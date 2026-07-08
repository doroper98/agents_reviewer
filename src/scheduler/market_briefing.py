"""Market Close Briefing Scheduler — v5.5.9.

장마감 후 (디폴트 18:30 KST) 한국 주식시장의 *구조 해석* 보고서를 자동 생성·송신.
``daily_briefing`` (06:00 매크로/지정학 브리핑) 과 별개 토픽 + 별개 시각 + 별개 구독자.

설계 원칙:
- pykrx 거래일 가드 — 휴장일 (주말/공휴일/임시휴장) 이면 발행 스킵.
- 페르소나 주입 — ``MARKET_BRIEFING_PERSONA_PATH`` 파일을 startup 시 1회 읽어
  event_description *앞* 에 박음 (사용자 선택: 페르소나 prime 우선).
- 같은 날 중복 트리거 방지 — ``market_brief_runs`` 의 ``run_date`` PK guard.
- 봇 프로세스 안 asyncio task — 별도 cron 불요.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from src.orchestrator import Orchestrator
    from src.scheduler.subscriptions import MarketBriefSubscriberRegistry
    from src.token_budget import AnalysisMode

logger = logging.getLogger(__name__)


SendTextFn = Callable[[int, str], Awaitable[None]]
SendDocumentFn = Callable[[int, str, str], Awaitable[None]]


def _load_persona(path: str | None) -> str:
    """Read persona markdown file at startup. Empty string if missing/disabled."""
    if not path:
        return ""
    if not os.path.isfile(path):
        logger.warning(
            "[scheduler] MARKET_BRIEFING_PERSONA_PATH=%s not found — proceeding without persona",
            path,
        )
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.warning("[scheduler] persona load failed (%s): %s", path, e)
        return ""


def _is_krx_trading_day(today: date) -> tuple[bool, str | None]:
    """오늘이 KRX 거래일인지 판단. pykrx 거래일 캘린더 사용.

    Returns: (거래일 여부, 휴장 사유). 사유는 'weekend' / 'holiday' / None.
    pykrx 가 없거나 호출 실패하면 *평일이면 거래일로 가정* (fail-open) + warning.
    """
    # 빠른 가드: 주말.
    if today.weekday() >= 5:
        return False, "weekend"
    try:
        from pykrx import stock as krx_stock
        # get_nearest_business_day_in_a_week(today) 가 today 와 같으면 거래일.
        today_str = today.strftime("%Y%m%d")
        nearest = krx_stock.get_nearest_business_day_in_a_week(today_str)
        if nearest == today_str:
            return True, None
        return False, "holiday"
    except Exception as e:
        logger.warning(
            "[scheduler] pykrx trading-day check failed (%s); assuming trading day", e,
        )
        return True, None


def _build_market_briefing_prompt(now_local: datetime, persona: str) -> str:
    """페르소나 + 시장 브리핑 요청. 페르소나가 *앞에* 위치 (사용자 결정)."""
    today_str = now_local.strftime("%Y-%m-%d (%a)")
    cutoff_str = now_local.strftime("%H:%M")
    tz_label = (
        now_local.tzinfo.key if hasattr(now_local.tzinfo, "key") else str(now_local.tzinfo)
    )

    request = (
        f"오늘 {today_str} {cutoff_str} {tz_label} 한국 주식장 마감 후 자동 브리핑 "
        f"(심층 구조 분석).\n\n"
        f"분석 대상: 오늘 KOSPI / KOSDAQ 정규장 마감 결과.\n\n"
        f"요구사항:\n"
        f"1. 웹 검색 + 시장 데이터 (KRX/Yahoo/FRED/ECOS 자동 fetch) 로 최신 종가·"
        f"거래대금·외인/기관/개인 수급·환율·금리·주요 섹터 지수를 확인.\n"
        f"2. **[제공 데이터] 입력 key_figures 에 KRX 실측 KOSPI200 선물·옵션 수치와 "
        f"시장 등락 종목 수(breadth)가 이미 들어 있다.** 선물 종가·베이시스·미결제약정, "
        f"VKOSPI, 풋/콜 비율, 옵션 max pain, 관심 콜·풋 행사가의 IV·그릭(델타/감마/세타/"
        f"베가/로), 코스피·코스닥 상승/하락/보합 종목 수와 하락비율(당일·5일·20일)이 그것이다. "
        f"이 수치를 *반드시 본문에 인용* 한다. 부족한 항목(주체별 선물 순매수·동시만기 일정 "
        f"등)은 증권사 데일리 파생 리포트·연합인포맥스·KRX 정보데이터시스템을 웹 검색해 "
        f"보완하되, 확보 못 하면 '확인되지 않음' 으로 둔다(추정 금지).\n"
        f"3. 본 페르소나의 11 렌즈를 적용해 *시장 구조 해석* 보고서 작성. "
        f"종목 추천 보고서가 아님. 가격·거래대금·수급·섹터 로테이션·거시 변수·뉴스 간의 "
        f"*관계* 를 풀어낸다. 단순 종가 나열 금지.\n"
        f"4. **[필수] 지수 선물·옵션만 다루는 독립된 전문 분석 섹션(별도 제목)을 반드시 "
        f"하나 포함** (제11 렌즈, 파생 데스크 전문가 수준). 제공된 실측치로 다음을 모두 다룬다: "
        f"① 선물 가격·베이시스와 차익거래 압력, ② **선물 수급 주체별 분해**(외국인/금융투자/"
        f"투신/연기금 등 누가 방향을 걸었나)와 현·선 정합성, ③ 미결제약정×가격 조합(신규/청산)·"
        f"프로그램, ④ **관심 콜·풋 행사가**(IV·거래량·미결제가 두드러진 행사가, 매물벽·스큐)와 "
        f"VKOSPI·풋콜비율·만기 구조, ⑤ **그리스(델타/감마/세타/베가/로) 기반 해석**(만기 임박 "
        f"감마·변동성 베가·시간가치 세타가 시장에 가하는 압력). 그릭 수치를 지어내지 말고 "
        f"제공된 값·관측 조건으로부터 시사점을 읽되, 미확인 항목도 개념·관전 포인트는 설명해 "
        f"섹션을 비우지 말 것.\n"
        f"5. **[필수] 시장 폭(등락 종목 수) 분석을 포함** (제4 렌즈). 제공된 코스피·코스닥 "
        f"상승/하락/보합 종목 수와 하락비율(당일·5일·20일 추세)로 *지수가 소수 대형주로 "
        f"올라도 체감 시장이 약한 좁은 장인지* 판정. 하락비율↔지수 상관이 제공되면 그 선행성 "
        f"한계도 함께 적는다(단정 금지 — 등락 종목 수는 대형주 지수와 괴리될 수 있음).\n"
        f"6. 최소 한 개의 핵심 가설 + 그 가설의 반증 조건 (제10 렌즈) 을 명시.\n"
        f"7. 마지막에 '내일 검증할 후속 신호' 3~5건과 데드라인 제시 "
        f"(감시 신호 시스템 등록 대상).\n"
    )

    if persona:
        return f"{persona}\n\n---\n\n{request}"
    return request


def _next_trigger(time_str: str, tz_name: str, now: datetime | None = None) -> datetime:
    """Next trigger datetime in tz (HH:MM)."""
    tz = ZoneInfo(tz_name)
    now_local = (now.astimezone(tz) if now is not None else datetime.now(tz))
    h, m = (int(x) for x in time_str.split(":", 1))
    today_target = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if today_target <= now_local:
        return today_target + timedelta(days=1)
    return today_target


async def run_market_briefing_loop(
    *,
    orchestrator: "Orchestrator",
    subscribers: "MarketBriefSubscriberRegistry",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    time_str: str = "18:30",
    tz_name: str = "Asia/Seoul",
    persona_path: str | None = None,
    enabled: bool = True,
) -> None:
    """Background loop. 봇 시작 시 ``asyncio.create_task(...)`` 로 띄움.

    daily_briefing 의 run_daily_briefing_loop 와 동일 패턴. 거래일 가드는
    트리거 시점에 평가 — 휴장이면 ``market_brief_runs`` 에 'weekend'/'holiday'
    사유 기록 후 skip.
    """
    persona = _load_persona(persona_path)
    persona_label = f"loaded ({len(persona)}자)" if persona else "none"
    logger.info(
        "[scheduler] Market briefing loop starting "
        "(enabled=%s, time=%s, tz=%s, subscribers=%d, persona=%s)",
        enabled, time_str, tz_name, subscribers.count(), persona_label,
    )

    while True:
        try:
            tz = ZoneInfo(tz_name)
            now_local = datetime.now(tz)
            next_dt = _next_trigger(time_str, tz_name, now=now_local)
            sleep_sec = max(1.0, (next_dt - now_local).total_seconds())
            logger.info(
                "[scheduler] Next market brief trigger at %s (%s) — sleeping %.0fs",
                next_dt.isoformat(), tz_name, sleep_sec,
            )
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            logger.info("[scheduler] Market briefing loop cancelled — shutting down")
            raise

        try:
            await _run_one_market_cycle(
                orchestrator=orchestrator,
                subscribers=subscribers,
                send_text_fn=send_text_fn,
                send_document_fn=send_document_fn,
                tz_name=tz_name,
                persona=persona,
                enabled=enabled,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "[scheduler] market brief cycle error: %s", e, exc_info=True,
            )


async def _run_one_market_cycle(
    *,
    orchestrator: "Orchestrator",
    subscribers: "MarketBriefSubscriberRegistry",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    tz_name: str,
    persona: str,
    enabled: bool,
) -> None:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    run_date = now_local.strftime("%Y-%m-%d")

    sub_list = subscribers.list_all()

    if not enabled:
        logger.info(
            "[scheduler] Market trigger at %s but MARKET_BRIEFING_ENABLED=false; "
            "skipping (would have analyzed for %d subscriber(s))",
            now_local.isoformat(), len(sub_list),
        )
        return
    if not sub_list:
        logger.info(
            "[scheduler] Market trigger at %s but no subscribers; skipping",
            now_local.isoformat(),
        )
        return

    # 거래일 가드.
    is_trading, skip_reason = _is_krx_trading_day(now_local.date())
    if not is_trading:
        if subscribers.start_run(run_date, subscribers=len(sub_list), skipped_reason=skip_reason):
            subscribers.finish_run(run_date, succeeded=0, failed=0)
        logger.info(
            "[scheduler] %s — KRX 휴장 (%s). 시장 브리핑 skip.",
            run_date, skip_reason,
        )
        return

    if not subscribers.start_run(run_date, subscribers=len(sub_list)):
        logger.info(
            "[scheduler] Market brief for %s already started — skipping duplicate trigger",
            run_date,
        )
        return

    prompt = _build_market_briefing_prompt(now_local, persona)
    logger.info(
        "[scheduler] Market brief cycle %s — %d subscriber(s), persona=%dchars",
        run_date, len(sub_list), len(persona),
    )

    succeeded = 0
    failed = 0
    for chat_id, mode in sub_list:
        try:
            await _market_brief_for_chat(
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
                "[scheduler] market brief for chat=%d failed: %s",
                chat_id, e, exc_info=True,
            )
            try:
                await send_text_fn(
                    chat_id,
                    f"❌ 시장 브리핑 ({run_date}) 생성 실패: {str(e)[:200]}",
                )
            except Exception:
                pass

    subscribers.finish_run(run_date, succeeded, failed)
    logger.info(
        "[scheduler] Market brief cycle %s done — success=%d failed=%d",
        run_date, succeeded, failed,
    )


async def _market_brief_for_chat(
    *,
    orchestrator: "Orchestrator",
    chat_id: int,
    prompt: str,
    mode: "AnalysisMode",
    send_text_fn: SendTextFn,
    send_document_fn: SendDocumentFn | None,
    run_date: str,
) -> None:
    mode_label = {"fast": "⚡ fast", "deep": "🔬 deep"}.get(mode, "🟢 standard")
    await send_text_fn(
        chat_id,
        f"📈 {run_date} 한국 장마감 브리핑 시작 ({mode_label} 모드)\n"
        f"  · 시장 구조 해석가 페르소나로 분석 중입니다.\n"
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
        # v7.9.0 — 장마감 브리핑 전용: KOSPI200 선물·옵션(그릭) + 시장 폭(등락 종목 수)
        # 실데이터를 KRX 에서 fetch 해 key_figures·차트로 주입. 다른 보고서엔 미적용.
        fetch_kr_market_internals=True,
    )

    # 텍스트 보고서 청크 + glossary 송신 제거 (v5.1.1 의 daily_briefing 도 추후 같은 정리
    # 필요하지만 일단 본 신규 모듈은 처음부터 노이즈 최소화 — URL + bundle 만).

    # v7.7.0 — X 구독자용 broadcast 요약 (라벨 없이 본문만, daily_briefing 과 동일 패턴).
    # 장마감 브리핑도 다른 보고서처럼 텔레그램 요약을 송신한다.
    try:
        broadcast = (
            result.composed_report.broadcast_summary.strip()
            if result.composed_report and result.composed_report.broadcast_summary
            else ""
        )
        if broadcast:
            await send_text_fn(chat_id, broadcast)
    except Exception as e:
        logger.warning("[scheduler] market brief broadcast summary send failed: %s", e)

    # 보고서 본문 .md 링크(🤖 AI 전달용 Markdown / 🤝 GitHub raw .md)는 제거 —
    # HTML 보고서 링크만 유지 (사용자 요청).
    if result.report_url and result.report_url.startswith("http"):
        await send_text_fn(
            chat_id,
            f"📈 한국 장마감 브리핑 ({run_date})\n\n"
            f"🔗 보고서: {result.report_url}",
        )
    elif result.report_path and os.path.isfile(result.report_path) and send_document_fn:
        await send_document_fn(
            chat_id,
            result.report_path,
            f"📈 장마감 브리핑 ({run_date}) — Cloudflare 업로드 실패, 파일 첨부",
        )

    # 영상 제작용 ReportBundle 자동 첨부 (v5.5.0 패턴).
    if result.report_path:
        bundle_path = result.report_path.replace(".html", ".bundle.json")
        if os.path.isfile(bundle_path) and send_document_fn:
            try:
                await send_document_fn(
                    chat_id, bundle_path,
                    "📦 영상 제작용 번들 (osint_generator)",
                )
            except Exception as e:
                logger.warning("[scheduler] bundle send failed: %s", e)

    duration = (
        f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"
    )
    await send_text_fn(chat_id, f"✅ 장마감 브리핑 완료 (소요시간: {duration}초)")
