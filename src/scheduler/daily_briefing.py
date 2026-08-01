"""Daily Briefing Scheduler — v5.1.0.

봇 프로세스 안에서 도는 asyncio task. 매일 ``DAILY_BRIEFING_TIME`` (``DAILY_BRIEFING_TZ``
기준) 에 깨어나, ``BriefingSubscriberRegistry`` 에 등록된 모든 채팅에 "간밤 산업/지정학/
정치/전쟁 이슈" 심층 보고서를 보낸다.

설계 원칙:
- 별도 cron 프로세스 X — 기존 watchlist monitor 와 동일한 in-process asyncio 패턴.
- 같은 날 중복 트리거 방지: ``briefing_runs`` 테이블에 ``run_date`` PRIMARY KEY 로 atomic guard.
- Per-subscriber 분석 — 각 chat_id 별로 ``Orchestrator.run_analysis()`` 를 ``mode='deep'``
  (또는 구독 시 지정한 모드) 로 호출. 이는 여러 채팅이 *각자의* watchlist 에 신호를
  등록받는 자연스러운 분리를 보장.
- v4.0.0 Tier 4 의 2-call 파이프라인 (ContextAnalyst + UnifiedComposer/NarrativeComposer)
  을 그대로 사용. mode='deep' 이 composer 프롬프트의 분석 깊이를 결정 (5~7 섹션 + 모순 명시).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Awaitable, Callable, TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from src.orchestrator import Orchestrator
    from src.scheduler.subscriptions import BriefingSubscriberRegistry
    from src.token_budget import AnalysisMode

logger = logging.getLogger(__name__)


# Send 콜백: (chat_id, text) → None. 텍스트 분할 안 함 — caller 가 알아서.
SendTextFn = Callable[[int, str], Awaitable[None]]
# Send 파일 콜백: (chat_id, file_path, caption) → None.
SendDocumentFn = Callable[[int, str, str], Awaitable[None]]


def _build_briefing_prompt(now_local: datetime) -> str:
    """간밤 (전날 자정 ~ 분석 시각) 산업/지정학/정치/전쟁 이슈 종합 분석 프롬프트.

    분석 시각은 보통 06:00 KST 이므로 "간밤" = 전날 자정 ~ 당일 06:00 부근.
    웹 검색은 ContextAnalyst 단계에서 자동 수행됨. "심층" 키워드를 프롬프트에 포함시키지만
    실제 mode 는 호출 시 명시적으로 전달 — 일관성을 위해.
    """
    today_str = now_local.strftime("%Y-%m-%d (%a)")
    yesterday = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")
    cutoff_str = now_local.strftime("%H:%M")
    tz_label = (
        now_local.tzinfo.key if hasattr(now_local.tzinfo, "key") else str(now_local.tzinfo)
    )
    return (
        f"오늘 {today_str} 아침 자동 일일 브리핑 (심층 분석).\n\n"
        f"분석 대상: {tz_label} 기준 {yesterday} 자정(00:00) 이후 ~ "
        f"오늘 {cutoff_str} 사이에 보도된 산업·지정학·정치·전쟁 이슈 종합.\n\n"
        f"요구사항:\n"
        f"1. 웹 검색으로 최신 보도를 직접 확인 (학습 데이터 의존 금지).\n"
        f"2. 위 4개 분야에서 가장 임팩트가 큰 3~5건을 선별.\n"
        f"3. 각 사건마다: (a) 사실관계 요약 (b) 핵심 행위자 (c) 한국 경제·증시·외교에 "
        f"미칠 직간접 영향 (d) 오늘 ({today_str}) 시장 개장/외교 일정에 미칠 즉시 영향.\n"
        f"4. 각 사건의 카테고리(산업/지정학/정치/전쟁) 명시.\n"
        f"5. 마지막에 '오늘 점검할 후속 신호' 3~5건과 데드라인 제시 "
        f"(감시 신호 시스템 등록 대상).\n"
    )


def _next_trigger(time_str: str, tz_name: str, now: datetime | None = None) -> datetime:
    """Compute next datetime (in tz) to trigger the briefing.

    Args:
        time_str: 'HH:MM' 24h.
        tz_name: IANA tz (예: 'Asia/Seoul').
        now: optional override (테스트용).
    """
    tz = ZoneInfo(tz_name)
    now_local = (now.astimezone(tz) if now is not None else datetime.now(tz))
    h, m = (int(x) for x in time_str.split(":", 1))
    today_target = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if today_target <= now_local:
        return today_target + timedelta(days=1)
    return today_target


async def run_daily_briefing_loop(
    *,
    orchestrator: "Orchestrator",
    subscribers: "BriefingSubscriberRegistry",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    time_str: str = "06:00",
    tz_name: str = "Asia/Seoul",
    enabled: bool = True,
) -> None:
    """Background loop. 봇 시작 시 ``asyncio.create_task(...)`` 로 띄움.

    enabled=False 라도 task 자체는 돌지만 트리거 시각에 실제 분석 실행을 스킵
    (구독자 수만 로깅). 이 이중 게이트 덕분에 ``DAILY_BRIEFING_ENABLED=false`` 가
    "스케줄러는 살아 있고 구독은 받지만 분석은 안 함" 의 운영 상태를 표현한다.
    """
    logger.info(
        "[scheduler] Daily briefing loop starting "
        "(enabled=%s, time=%s, tz=%s, subscribers=%d)",
        enabled, time_str, tz_name, subscribers.count(),
    )
    while True:
        try:
            tz = ZoneInfo(tz_name)
            now_local = datetime.now(tz)
            next_dt = _next_trigger(time_str, tz_name, now=now_local)
            sleep_sec = max(1.0, (next_dt - now_local).total_seconds())
            logger.info(
                "[scheduler] Next briefing trigger at %s (%s) — sleeping %.0fs",
                next_dt.isoformat(), tz_name, sleep_sec,
            )
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            logger.info("[scheduler] Daily briefing loop cancelled — shutting down")
            raise

        try:
            await _run_one_briefing_cycle(
                orchestrator=orchestrator,
                subscribers=subscribers,
                send_text_fn=send_text_fn,
                send_document_fn=send_document_fn,
                tz_name=tz_name,
                enabled=enabled,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("[scheduler] briefing cycle error: %s", e, exc_info=True)


async def _run_one_briefing_cycle(
    *,
    orchestrator: "Orchestrator",
    subscribers: "BriefingSubscriberRegistry",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    tz_name: str,
    enabled: bool,
) -> None:
    """Single trigger — fan out to all subscribers (sequential to protect VM memory)."""
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    run_date = now_local.strftime("%Y-%m-%d")

    sub_list = subscribers.list_all()
    if not enabled:
        logger.info(
            "[scheduler] Trigger fired at %s but DAILY_BRIEFING_ENABLED=false; "
            "skipping (would have analyzed for %d subscriber(s))",
            now_local.isoformat(), len(sub_list),
        )
        return
    if not sub_list:
        logger.info(
            "[scheduler] Trigger fired at %s but no subscribers; skipping",
            now_local.isoformat(),
        )
        return

    if not subscribers.start_run(run_date, subscribers=len(sub_list)):
        logger.info(
            "[scheduler] Run for %s already started — skipping duplicate trigger",
            run_date,
        )
        return

    prompt = _build_briefing_prompt(now_local)
    logger.info(
        "[scheduler] Briefing cycle %s — %d subscribers",
        run_date, len(sub_list),
    )

    succeeded = 0
    failed = 0
    for chat_id, mode in sub_list:
        try:
            await _briefing_for_chat(
                orchestrator=orchestrator,
                chat_id=chat_id,
                prompt=prompt,
                mode=mode,
                send_text_fn=send_text_fn,
                send_document_fn=send_document_fn,
                run_date=run_date,
            )
            succeeded += 1
        except asyncio.CancelledError:
            subscribers.finish_run(run_date, succeeded, failed)
            raise
        except Exception as e:
            failed += 1
            logger.warning(
                "[scheduler] briefing for chat=%d failed: %s",
                chat_id, e, exc_info=True,
            )
            try:
                await send_text_fn(
                    chat_id,
                    f"❌ 일일 브리핑 ({run_date}) 생성 실패: {str(e)[:200]}",
                )
            except Exception:
                pass

    subscribers.finish_run(run_date, succeeded, failed)
    logger.info(
        "[scheduler] Briefing cycle %s done — success=%d failed=%d",
        run_date, succeeded, failed,
    )


async def _briefing_for_chat(
    *,
    orchestrator: "Orchestrator",
    chat_id: int,
    prompt: str,
    mode: "AnalysisMode",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    run_date: str,
) -> None:
    """Run the orchestrator for one subscriber and ship the report to that chat.

    Mirrors ``TelegramBot._run_analysis`` send sequence (text report → glossary → URL).
    """
    mode_label = {"fast": "⚡ fast", "deep": "🔬 deep"}.get(mode, "🟢 standard")
    await send_text_fn(
        chat_id,
        f"🌅 {run_date} 일일 브리핑 시작 ({mode_label} 모드)\n"
        f"  · 간밤 산업·지정학·정치·전쟁 이슈를 자동 분석 중입니다.\n"
        f"  · 수 분 정도 소요됩니다.",
    )

    async def status_callback(status: str) -> None:
        try:
            await send_text_fn(chat_id, status)
        except Exception as e:
            logger.warning("[scheduler] status send failed for chat=%d: %s", chat_id, e)

    result = await orchestrator.run_analysis(
        event_description=prompt,
        chat_id=chat_id,
        status_callback=status_callback,
        mode=mode,
        # v8.5.3 — 보고서 목록 [일일브리핑] 배지 판별용 출처 표식.
        report_kind="daily_briefing",
    )

    # 1) Text report (best-effort, chunked).
    try:
        text_report = orchestrator._build_text_report(result)
        for i in range(0, len(text_report), 3900):
            await send_text_fn(chat_id, text_report[i:i + 3900])
    except Exception as e:
        logger.warning("[scheduler] text report send failed: %s", e)

    # 2) Glossary (best-effort, chunked).
    try:
        glossary_text = orchestrator._build_glossary_text(result)
        if glossary_text:
            for i in range(0, len(glossary_text), 3900):
                await send_text_fn(chat_id, glossary_text[i:i + 3900])
    except Exception as e:
        logger.warning("[scheduler] glossary send failed: %s", e)

    # 2.5) v5.6.1 — X 구독자용 broadcast 요약 (라벨 없이 본문만).
    try:
        broadcast = (
            result.composed_report.broadcast_summary.strip()
            if result.composed_report and result.composed_report.broadcast_summary
            else ""
        )
        if broadcast:
            await send_text_fn(chat_id, broadcast)
    except Exception as e:
        logger.warning("[scheduler] broadcast summary send failed: %s", e)

    # 3) Report URL (must reach the user).
    # Phase V6-7/b — 검수 바이라인 (검수 수행 시만).
    _verif = (result.composed_report.verification if result.composed_report else None) or {}
    _verif_line = f"\n🔎 {_verif['text']}" if _verif.get("text") else ""
    # 보고서 본문 .md 링크(🤖 AI 전달용 Markdown / 🤝 GitHub raw .md)는 제거 —
    # HTML 보고서 링크만 유지 (사용자 요청).
    if result.report_url and result.report_url.startswith("http"):
        await send_text_fn(
            chat_id,
            f"📊 일일 브리핑 ({run_date})\n\n"
            f"🔗 보고서 링크: {result.report_url}"
            f"{_verif_line}",
        )
    elif result.report_path and os.path.isfile(result.report_path) and send_document_fn:
        await send_document_fn(
            chat_id,
            result.report_path,
            f"📊 일일 브리핑 ({run_date}) — Cloudflare 업로드 실패, 파일 첨부",
        )

    duration = (
        f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"
    )
    await send_text_fn(chat_id, f"✅ 일일 브리핑 완료 (소요시간: {duration}초)")
