"""Telegram bot integration for the Event Analysis Team."""

from __future__ import annotations

import logging
import os
import time
import glob
import json
import asyncio
import shutil
from collections import deque
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import Config
from src.orchestrator import Orchestrator
from src.models import MAX_CHAIN_DEPTH, ParentContext, WatchSignal
from src.watchlist import WatchlistRegistry, run_monitor_loop
from src.watchlist.monitor import format_telegram_alert
from src.scheduler import BriefingSubscriberRegistry, run_daily_briefing_loop

logger = logging.getLogger(__name__)

# V3 Step 5-B (v2.9.5): default DB path. Config 에 별도 필드를 추가하지 않음 — 보고서 출력
# 디렉토리 옆에 둠 (운영 자연스러움 + git ignored).
DEFAULT_WATCHLIST_DB_NAME = "watchlist.db"
# v5.1.0 — 일일 브리핑 구독 / 실행 이력 DB. watchlist 와 분리해 관심사 격리.
DEFAULT_SCHEDULER_DB_NAME = "scheduler.db"

# Track bot start time and analysis count
_bot_start_time: float = 0.0
_analysis_count: int = 0


@dataclass
class QueueItem:
    """A queued analysis request.

    v5.1.1: ``update`` 가 None 이면 자동 후속 분석 — ``chat_id`` + ``parent_context`` 사용.
    """
    event_text: str
    update: Update | None = None
    chat_id: int = 0
    parent_context: ParentContext | None = None
    position: int = 0


class TelegramBot:
    """Telegram bot that receives analysis commands and sends reports."""

    def __init__(self, config: Config) -> None:
        self.config = config
        # V3 Step 5-B (v2.9.5): Watchlist registry — bot 프로세스 안에서 공유.
        db_path = os.path.join(config.report_output_dir, DEFAULT_WATCHLIST_DB_NAME)
        self.watchlist_registry = WatchlistRegistry(db_path)
        # v5.1.0: Briefing subscription registry — daily scheduler 가 공유.
        scheduler_db_path = os.path.join(
            config.report_output_dir, DEFAULT_SCHEDULER_DB_NAME,
        )
        self.briefing_registry = BriefingSubscriberRegistry(scheduler_db_path)
        self.orchestrator = Orchestrator(config, watchlist_registry=self.watchlist_registry)
        self._queue: deque[QueueItem] = deque()
        self._is_analyzing: bool = False
        self._current_topic: str = ""
        # v3.4.2: 진행 중 분석의 asyncio task 핸들. /stop /stopall 이 cancel 호출.
        self._current_task: asyncio.Task | None = None
        # asyncio task handle for the monitor loop — populated in post_init.
        self._monitor_task: asyncio.Task | None = None
        # v5.1.0: asyncio task handle for the daily briefing scheduler loop.
        self._briefing_task: asyncio.Task | None = None
        # Application reference for telegram message sending from monitor task.
        self._app: Application | None = None
        global _bot_start_time
        _bot_start_time = time.time()

    def _is_authorized(self, chat_id: int) -> bool:
        """Check if chat is authorized. Empty list = allow all."""
        if not self.config.allowed_chat_ids:
            return True
        return chat_id in self.config.allowed_chat_ids

    async def _start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        if update.message is None:
            return
        await update.message.reply_text(
            "📊 Event Analysis Team\n\n"
            "분석할 사건이나 상황을 메시지로 보내주세요.\n"
            "6명의 AI 분석관이 종합 보고서를 작성합니다.\n\n"
            "명령어:\n"
            "/analyze <주제> — 분석 시작 (보고서 + md + 영상용 bundle.json 자동 전송)\n"
            "/bundle <report_id> — 기존 보고서의 bundle.json 재생성·전송\n"
            "/stop — 진행 중 분석 중단 (v3.4.2)\n"
            "/stopall — 진행 중 분석 + 대기열 전체 비우기 (v3.4.2)\n"
            "/status — 서버 상태 확인\n"
            "/reports — 전체 보고서 목록\n"
            "/queue — 대기열 확인\n"
            "/watchlist — 활성 감시 신호 목록 (v2.9.5)\n"
            "/fire <signal_id> [direction] — 신호 수동 발화 (v2.9.5)\n"
            "/briefing_on — 일일 브리핑 구독 (v5.1.0)\n"
            "/briefing_off — 일일 브리핑 구독 해제\n"
            "/briefing_status — 일일 브리핑 설정 확인\n"
            "? <질문> — 간단 질답\n"
            "/start — 이 메시지 표시"
        )

    async def _stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """v3.4.2 — 진행 중 분석만 중단. 대기열은 보존."""
        if update.message is None or update.effective_chat is None:
            return
        if not self._is_authorized(update.effective_chat.id):
            return
        if not self._is_analyzing or self._current_task is None or self._current_task.done():
            await update.message.reply_text("실행 중인 분석이 없습니다.")
            return
        topic = self._current_topic[:50]
        queue_left = len(self._queue)
        self._current_task.cancel()
        tail = f"\n📋 대기열 {queue_left}건 은 그대로 유지." if queue_left else ""
        await update.message.reply_text(
            f"🛑 분석 중단 요청 보냄: {topic}\n정리 후 곧 종료됩니다.{tail}"
        )

    async def _stopall_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """v3.4.2 — 진행 중 분석 + 대기열 전체 비우기."""
        if update.message is None or update.effective_chat is None:
            return
        if not self._is_authorized(update.effective_chat.id):
            return
        had_running = self._is_analyzing and self._current_task is not None and not self._current_task.done()
        cleared = len(self._queue)
        self._queue.clear()
        if had_running:
            assert self._current_task is not None  # for type checker
            topic = self._current_topic[:50]
            self._current_task.cancel()
            await update.message.reply_text(
                f"🛑 전체 중단: 진행 중 분석 ({topic}) 취소 + 대기열 {cleared}건 비움."
            )
        elif cleared:
            await update.message.reply_text(f"📋 대기열 {cleared}건 비움. 진행 중 분석은 없었음.")
        else:
            await update.message.reply_text("실행 중인 분석도, 대기열도 없습니다.")

    async def _status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        if update.message is None:
            return

        global _bot_start_time, _analysis_count

        uptime_sec = time.time() - _bot_start_time if _bot_start_time else 0
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        uptime_str = f"{hours}시간 {minutes}분"

        report_dir = self.config.report_output_dir
        report_files = glob.glob(os.path.join(report_dir, "analysis_*.html")) if os.path.isdir(report_dir) else []
        report_count = len(report_files)

        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            total = int([l for l in meminfo.split("\n") if "MemTotal" in l][0].split()[1])
            available = int([l for l in meminfo.split("\n") if "MemAvailable" in l][0].split()[1])
            mem_pct = int((1 - available / total) * 100)
            mem_str = f"{mem_pct}% 사용"
        except Exception:
            mem_str = "확인 불가"

        analyzing_str = f"분석 중: {self._current_topic[:30]}" if self._is_analyzing else "대기 중"
        queue_str = f"{len(self._queue)}건 대기" if self._queue else "없음"

        from src.orchestrator import VERSION, BUILD_INFO

        # v3.4.1 — 어떤 브랜치/커밋이 실제로 돌고 있는지 보여줘서
        # "pull 만 하고 재기동 안 함" 류 디버깅을 즉시 종결한다.
        dirty_mark = "  ⚠️ uncommitted" if BUILD_INFO.get("dirty") else ""
        build_str = (
            f"  브랜치: {BUILD_INFO.get('branch', '?')}\n"
            f"  커밋: {BUILD_INFO.get('commit', '?')} "
            f"({BUILD_INFO.get('commit_date', '?')}){dirty_mark}\n"
        )

        # v5.1.0 — daily briefing 정보
        briefing_subs = self.briefing_registry.count()
        briefing_enabled = "✅" if self.config.daily_briefing_enabled else "❌"
        briefing_info = (
            f"  일일 브리핑: {briefing_enabled} {self.config.daily_briefing_time} "
            f"({self.config.daily_briefing_tz}) · 구독자 {briefing_subs}명"
        )

        status_msg = (
            f"✅ 봇 실행 중 — {VERSION}\n\n"
            f"{build_str}"
            f"  가동시간: {uptime_str}\n"
            f"  생성된 보고서: {report_count}건\n"
            f"  이번 세션 분석: {_analysis_count}건\n"
            f"  서버 메모리: {mem_str}\n"
            f"  현재 상태: {analyzing_str}\n"
            f"  대기열: {queue_str}\n"
            f"{briefing_info}"
        )

        await update.message.reply_text(status_msg)

    async def _queue_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /queue command — show current queue status."""
        if update.message is None:
            return

        lines = []
        if self._is_analyzing:
            lines.append(f"🔄 분석 중: {self._current_topic[:50]}")
        else:
            lines.append("⏸ 분석 대기 중")

        if self._queue:
            lines.append(f"\n📋 대기열 ({len(self._queue)}건):")
            for i, item in enumerate(self._queue, 1):
                lines.append(f"  {i}. {item.event_text[:40]}")
        else:
            lines.append("\n대기열 비어있음")

        await update.message.reply_text("\n".join(lines))

    async def _reports_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /reports command."""
        if update.message is None:
            return
        project = self.config.cloudflare_project_name
        await update.message.reply_text(
            f"📁 전체 보고서 목록:\nhttps://{project}.pages.dev/"
        )

    # ------------------------------------------------------------------
    # V3 Step 5-B (v2.9.5) — Watchlist commands
    # ------------------------------------------------------------------

    async def _watchlist_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/watchlist`` — 이 채팅에 등록된 활성(미발화) 감시 신호 목록."""
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        signals = self.watchlist_registry.list_active_for_chat(chat_id)
        if not signals:
            await update.message.reply_text(
                "📒 활성 감시 신호 없음.\n"
                "분석을 실행하면 보고서의 watch_signals 가 자동 등록됨."
            )
            return
        lines = [f"📒 활성 감시 신호 {len(signals)}건:"]
        for sig in signals:
            lines.append(
                f"\n• `{sig.signal_id}`\n"
                f"  {sig.description}\n"
                f"  방향: {sig.direction} · 데드라인: {sig.deadline}"
            )
        lines.append("\n수동 발화: /fire <signal_id> [direction]")
        await update.message.reply_text("\n".join(lines))

    async def _fire_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/fire <signal_id> [direction]`` — 수동 발화. direction 생략 시 기존 방향 유지."""
        if update.message is None or update.effective_chat is None:
            return
        args = list(context.args) if context.args else []
        if not args:
            await update.message.reply_text("사용법: /fire <signal_id> [direction]")
            return
        signal_id = args[0]
        new_direction = args[1] if len(args) >= 2 else None
        if new_direction and new_direction not in ("confirms_base", "rejects_base", "ambiguous"):
            await update.message.reply_text(
                f"잘못된 direction: {new_direction!r}. "
                "허용: confirms_base | rejects_base | ambiguous"
            )
            return
        # Authorization: 발화 요청자 chat_id 가 신호의 parent_chat_id 와 같아야 함.
        existing = self.watchlist_registry.get(signal_id)
        if existing is None:
            await update.message.reply_text(f"신호를 찾을 수 없음: {signal_id}")
            return
        if existing.parent_chat_id and existing.parent_chat_id != update.effective_chat.id:
            await update.message.reply_text("권한 없음 (다른 채팅의 신호).")
            return
        if existing.fired:
            await update.message.reply_text(
                f"이미 발화된 신호 ({existing.fired_at}). direction={existing.direction}"
            )
            return
        updated = self.watchlist_registry.mark_fired(
            signal_id, new_direction=new_direction,
        )
        if updated is None:
            await update.message.reply_text("발화 실패 — DB 업데이트가 0건.")
            return
        await update.message.reply_text(
            f"✅ 신호 발화 완료\n"
            f"`{updated.signal_id}` · 방향={updated.direction} · 시각={updated.fired_at}"
        )
        # 신호 발화 알림도 동시 송신 (parent_chat_id 로 broadcast — 본 채팅과 동일).
        try:
            await self._notify_signal_fired(updated)
        except Exception as e:
            logger.warning("[telegram_bot] /fire notify error: %s", e)

    async def _send_to_chat(self, chat_id: int, text: str) -> None:
        """Bot Application 을 통한 통일 전송 (Update 객체 없는 자동 후속 경로용, v5.1.1)."""
        if self._app is None or not chat_id:
            return
        try:
            await self._app.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.warning("[telegram_bot] send_message failed for chat=%d: %s", chat_id, e)

    async def _notify_signal_fired(self, signal: WatchSignal) -> None:
        """신호 발화 시 ①텔레그램 알림 ②chain_depth < MAX 면 후속 분석 자동 enqueue (v5.1.1)."""
        if self._app is None:
            logger.warning("[telegram_bot] notify called before app init; skipping")
            return
        if not signal.parent_chat_id:
            logger.warning(
                "[telegram_bot] signal %s has no parent_chat_id; cannot notify",
                signal.signal_id,
            )
            return
        text = format_telegram_alert(signal, parent_title=signal.parent_report_id)
        await self._send_to_chat(signal.parent_chat_id, text)

        # v5.1.1: 자동 후속 분석 트리거 — 부모(0)/자식(1) 발화까지만 자동 후속, 손자(2)+ 차단.
        try:
            await self._maybe_enqueue_followup(signal)
        except Exception as e:
            logger.warning(
                "[telegram_bot] followup enqueue error for %s: %s",
                signal.signal_id, e,
            )

    async def _maybe_enqueue_followup(self, signal: WatchSignal) -> None:
        """발화된 신호로부터 ParentContext 를 조립하고 후속 분석을 큐에 추가 (v5.1.1).

        ``signal.chain_depth`` 가 부모의 깊이. 자식 깊이는 +1. ``>= MAX_CHAIN_DEPTH``
        면 후속 자동 생성을 스킵하고 안내만 송신.
        """
        next_depth = signal.chain_depth + 1
        if next_depth >= MAX_CHAIN_DEPTH:
            logger.info(
                "[telegram_bot] signal %s at chain_depth=%d; skip auto-followup (cap=%d)",
                signal.signal_id, signal.chain_depth, MAX_CHAIN_DEPTH,
            )
            # v5.4.9: MAX_CHAIN_DEPTH=0 이라 모든 신호가 여기로 — 메시지에서 depth
            # 표기는 의미 없으므로 "자동 후속 분석 기능 비활성화" 로 단순화.
            if MAX_CHAIN_DEPTH == 0:
                msg = (
                    f"ℹ️ 신호 `{signal.signal_id}` 발화 — 자동 후속 분석 "
                    f"기능이 비활성화되어 있습니다. 필요 시 수동으로 분석을 "
                    f"요청하세요."
                )
            else:
                msg = (
                    f"ℹ️ 신호 `{signal.signal_id}` 의 후속 보고서는 체인 상한"
                    f"(depth={MAX_CHAIN_DEPTH})에 도달해 자동 생성하지 않습니다. "
                    f"필요 시 수동으로 분석을 요청하세요."
                )
            await self._send_to_chat(signal.parent_chat_id, msg)
            return

        meta = self.watchlist_registry.get_report_meta(signal.parent_report_id) or {}
        parent_event_desc = meta.get("event_description", "")
        parent_scenarios = meta.get("scenarios", [])

        parent_context = ParentContext(
            parent_report_id=signal.parent_report_id,
            parent_report_url=signal.parent_report_url,
            parent_event_description=parent_event_desc,
            parent_scenarios=parent_scenarios,
            triggering_signal=signal,
            chain_depth=signal.chain_depth,
        )

        parent_event_short = (parent_event_desc or signal.parent_report_id)[:300]
        event_description = (
            f"[후속 분석] 부모 보고서: {signal.parent_report_id}\n"
            f"발화된 감시 신호: {signal.description} (방향: {signal.direction})\n"
            f"원 이벤트: {parent_event_short}"
        )

        await self._send_to_chat(
            signal.parent_chat_id,
            f"🔄 후속 분석 자동 시작 — 부모: {signal.parent_report_id}\n"
            f"  발화 신호: {signal.description}",
        )

        if self._is_analyzing:
            position = len(self._queue) + 1
            self._queue.append(QueueItem(
                event_text=event_description,
                update=None,
                chat_id=signal.parent_chat_id,
                parent_context=parent_context,
                position=position,
            ))
            await self._send_to_chat(
                signal.parent_chat_id,
                f"📋 후속 분석 대기열 추가 ({position}번째)",
            )
        else:
            await self._run_analysis(
                update=None,
                event_text=event_description,
                chat_id=signal.parent_chat_id,
                parent_context=parent_context,
            )

    # ------------------------------------------------------------------
    # v5.1.0 — Daily Briefing commands
    # ------------------------------------------------------------------

    async def _briefing_on_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/briefing_on`` — 이 채팅을 일일 브리핑 수신처로 등록 (mode=deep 고정)."""
        if update.message is None or update.effective_chat is None:
            return
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized.")
            return
        chat_id = update.effective_chat.id
        newly = self.briefing_registry.subscribe(chat_id, mode="deep")
        time_str = self.config.daily_briefing_time
        tz_name = self.config.daily_briefing_tz
        enabled = self.config.daily_briefing_enabled
        head = (
            "✅ 일일 브리핑 구독 완료"
            if newly
            else "ℹ 이미 구독 중 (모드 갱신만 적용)"
        )
        enabled_str = (
            "활성"
            if enabled
            else "비활성 (서버 .env DAILY_BRIEFING_ENABLED=false)"
        )
        await update.message.reply_text(
            f"{head}\n\n"
            f"  · 트리거: 매일 {time_str} ({tz_name})\n"
            f"  · 모드: 🔬 deep (Tier 4 2-call 파이프라인, 5~7 섹션 + 모순 명시)\n"
            f"  · 분석 범위: 간밤 산업·지정학·정치·전쟁 이슈\n"
            f"  · 스케줄러 상태: {enabled_str}\n\n"
            f"해제: /briefing_off"
        )

    async def _briefing_off_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/briefing_off`` — 이 채팅의 일일 브리핑 구독 해제."""
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        removed = self.briefing_registry.unsubscribe(chat_id)
        if removed:
            await update.message.reply_text("✅ 일일 브리핑 구독 해제됨.")
        else:
            await update.message.reply_text("ℹ 구독 중이 아니었습니다.")

    async def _briefing_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/briefing_status`` — 이 채팅의 구독 상태 + 스케줄러 설정."""
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        subscribed = self.briefing_registry.is_subscribed(chat_id)
        total_subs = self.briefing_registry.count()
        time_str = self.config.daily_briefing_time
        tz_name = self.config.daily_briefing_tz
        enabled = self.config.daily_briefing_enabled
        sub_str = "✅ 구독 중" if subscribed else "❌ 미구독"
        enabled_str = "✅ 활성" if enabled else "❌ 비활성 (.env)"
        await update.message.reply_text(
            f"📒 일일 브리핑 상태\n\n"
            f"  · 이 채팅: {sub_str}\n"
            f"  · 전체 구독자 수: {total_subs}\n"
            f"  · 트리거: 매일 {time_str} ({tz_name})\n"
            f"  · 스케줄러: {enabled_str}\n"
            f"  · 모드: 🔬 deep\n\n"
            f"구독: /briefing_on · 해제: /briefing_off"
        )

    async def _analyze_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /analyze command."""
        if update.message is None or update.effective_chat is None:
            return

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized.")
            return

        text = " ".join(context.args) if context.args else ""
        if not text:
            await update.message.reply_text(
                "사용법: /analyze <분석할 사건 또는 주제>"
            )
            return

        await self._enqueue_analysis(update, text)

    async def _bundle_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """``/bundle <report_id>`` — 기존 보고서에서 ReportBundle 재emit + 재배포 (v5.5.0).

        저장된 analysis_{id}.json (FullAnalysisResult dump) 을 읽어 ReportBundle 로
        매핑 → analysis_{id}.bundle.json 작성 → reports/ 디렉토리 재배포.
        """
        if update.message is None or update.effective_chat is None:
            return
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized.")
            return
        if not self.config.enable_report_bundle:
            await update.message.reply_text("ReportBundle 비활성화됨 (V5_REPORT_BUNDLE=0).")
            return
        if not context.args:
            await update.message.reply_text("사용법: /bundle <report_id> (예: 20260525_090000)")
            return

        stem = context.args[0].strip()
        if stem.startswith("analysis_"):
            stem = stem[len("analysis_"):]
        for suf in (".bundle.json", ".json", ".html"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
        output_dir = self.config.report_output_dir
        json_path = os.path.join(output_dir, f"analysis_{stem}.json")
        if not os.path.exists(json_path):
            await update.message.reply_text(f"보고서 JSON 없음: analysis_{stem}.json")
            return

        msg = await update.message.reply_text(f"📦 번들 생성 중: analysis_{stem}")
        try:
            from src.models import FullAnalysisResult
            from src.handoff.bundle_builder import build_report_bundle

            with open(json_path, "r", encoding="utf-8") as f:
                result = FullAnalysisResult.model_validate(json.load(f))

            project = self.config.cloudflare_project_name or ""
            html_filename = f"analysis_{stem}.html"
            predicted = (
                f"https://{project}.pages.dev/{html_filename}" if project
                else (result.report_url or "")
            )
            # v5.5.7 — to_thread: prerender 의 sync Playwright 를 async 루프 밖에서 실행.
            bundle = await asyncio.to_thread(
                build_report_bundle,
                result, html_url=predicted,
                system_version=result.system_version or "",
                prerender_svg=getattr(self.config, "enable_bundle_prerender", True),
            )
            bundle_path = os.path.join(output_dir, f"analysis_{stem}.bundle.json")
            with open(bundle_path, "w", encoding="utf-8") as f:
                json.dump(bundle.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

            html_path = os.path.join(output_dir, html_filename)
            deploy_target = html_path if os.path.exists(html_path) else bundle_path
            await self.orchestrator.report_synthesizer._upload_to_cloudflare(deploy_target)

            bundle_url = (
                f"https://{project}.pages.dev/analysis_{stem}.bundle.json" if project
                else bundle_path
            )
            await msg.edit_text(
                f"✅ 번들 생성·배포 완료\n"
                f"  차트 {len(bundle.charts)} · 신호 {len(bundle.signals)} · 출처 {len(bundle.sources)}\n"
                f"  {bundle_url}"
            )
            # 영상 제작용 파일 자체도 첨부 (osint_generator 에 바로 넘길 수 있게).
            try:
                with open(bundle_path, "rb") as bf:
                    await update.message.reply_document(
                        document=bf, filename=f"analysis_{stem}.bundle.json",
                        caption="📦 영상 제작용 번들 (osint_generator)",
                    )
            except Exception as e:
                logger.warning("[telegram_bot] /bundle attach failed: %s", e)
        except Exception as e:
            logger.warning("[telegram_bot] /bundle error: %s", e)
            await msg.edit_text(f"번들 생성 실패: {e}")

    async def _message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle plain text messages."""
        if update.message is None or update.effective_chat is None:
            return

        if not self._is_authorized(update.effective_chat.id):
            return

        text = update.message.text
        if not text or not text.strip():
            return

        text = text.strip()

        if text.startswith("?"):
            question = text[1:].strip()
            if question:
                await self._quick_question(update, question)
                return

        await self._enqueue_analysis(update, text)

    async def _enqueue_analysis(self, update: Update, event_text: str) -> None:
        """Add analysis to queue and process if not already running."""
        if self._is_analyzing:
            position = len(self._queue) + 1
            self._queue.append(QueueItem(event_text=event_text, update=update, position=position))
            await update.message.reply_text(
                f"📋 대기열에 추가됨 ({position}번째)\n"
                f"  주제: {event_text[:50]}\n"
                f"  현재 분석 중: {self._current_topic[:40]}\n\n"
                f"완료되면 순서대로 시작됩니다."
            )
            return

        await self._run_analysis(update, event_text)

    async def _process_queue(self) -> None:
        """Process next item in queue if available."""
        if not self._queue:
            return

        next_item = self._queue.popleft()
        # Notify remaining queue items of updated position
        for i, item in enumerate(self._queue):
            item.position = i + 1

        await self._run_analysis(
            update=next_item.update,
            event_text=next_item.event_text,
            chat_id=next_item.chat_id or None,
            parent_context=next_item.parent_context,
        )

    async def _quick_question(self, update: Update, question: str) -> None:
        """Answer a quick question directly via Claude CLI/API."""
        if update.message is None:
            return

        msg = await update.message.reply_text("💬 답변 준비 중...")

        try:
            claude_bin = shutil.which("claude")
            if claude_bin is None:
                await msg.edit_text("claude CLI를 찾을 수 없습니다.")
                return

            cmd = [
                claude_bin,
                "-p", f"간결하게 답변. 음슴체. 핵심만.\n\n질문: {question}",
                "--output-format", "text",
                "--model", self.config.model_name,
                "--dangerously-skip-permissions",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                await msg.edit_text(f"답변 실패: {stderr.decode()[:200]}")
                return

            answer = stdout.decode().strip().replace("**", "")
            if len(answer) > 4000:
                answer = answer[:4000] + "..."

            await msg.edit_text(answer)

        except Exception as e:
            await msg.edit_text(f"답변 실패: {str(e)[:200]}")

    async def _run_analysis(
        self,
        update: Update | None,
        event_text: str,
        chat_id: int | None = None,
        parent_context: ParentContext | None = None,
    ) -> None:
        """Execute the analysis pipeline and send report.

        v5.1.1 two invocation modes:
        - User-triggered: ``update`` 가 실제 Update. chat_id, reply 모두 update 에서 추출.
        - Auto follow-up: ``update`` 가 None. ``chat_id`` 와 ``parent_context`` 명시 전달.
          메시지는 ``self._app.bot.send_message`` 로 송신.
        """
        if update is not None:
            if update.message is None or update.effective_chat is None:
                return
            chat_id = update.effective_chat.id
        else:
            if not chat_id:
                logger.warning("[telegram_bot] _run_analysis called without update or chat_id")
                return

        self._is_analyzing = True
        self._current_topic = event_text
        # v3.4.2 — /stop /stopall 이 cancel() 호출할 수 있게 task 핸들 보관.
        self._current_task = asyncio.current_task()

        async def send(text: str) -> None:
            """Update 있으면 reply_text, 없으면 bot.send_message 로 통일 전송."""
            if update is not None and update.message is not None:
                try:
                    await update.message.reply_text(text)
                except Exception:
                    pass
            else:
                await self._send_to_chat(chat_id, text)

        async def status_callback(status: str) -> None:
            await send(status)

        try:
            result = await self.orchestrator.run_analysis(
                event_description=event_text,
                chat_id=chat_id,
                status_callback=status_callback,
                parent_context=parent_context,
            )

            # v5.1.1: 텍스트 보고서 청크 + glossary 송신 제거 — 본문 콘텐츠는 보고서 HTML 안에 있음.
            # 텔레그램에는 URL + 후속 안내만 송신해 노이즈를 줄임.

            report_path = result.report_path
            followup_tag = " (후속)" if parent_context is not None else ""
            if result.report_url and result.report_url.startswith("http"):
                md_url = result.report_url.replace(".html", ".md")
                await send(
                    f"📊 Full Analysis Report{followup_tag}\n\n"
                    f"🔗 보고서 링크: {result.report_url}\n"
                    f"🤖 AI 전달용 (Markdown): {md_url}"
                )
            elif report_path and os.path.isfile(report_path):
                # Fallback: send file only if Cloudflare upload failed
                if update is not None and update.message is not None:
                    with open(report_path, "rb") as f:
                        await update.message.reply_document(
                            document=f,
                            filename=os.path.basename(report_path),
                            caption=f"📊 Full Analysis Report{followup_tag} (외부링크 생성 실패 — 파일 첨부)",
                        )
                elif self._app is not None:
                    try:
                        with open(report_path, "rb") as f:
                            await self._app.bot.send_document(
                                chat_id=chat_id,
                                document=f,
                                filename=os.path.basename(report_path),
                                caption=f"📊 후속 분석 보고서{followup_tag} (외부링크 생성 실패 — 파일 첨부)",
                            )
                    except Exception as e:
                        logger.warning("[telegram_bot] send_document failed: %s", e)

            # v5.5.3 — 영상 제작용 ReportBundle 자동 첨부 (osint_generator). 항상 동반.
            bundle_path = report_path.replace(".html", ".bundle.json") if report_path else ""
            if bundle_path and os.path.isfile(bundle_path):
                bundle_cap = "📦 영상 제작용 번들 (osint_generator)"
                if result.report_url and result.report_url.startswith("http"):
                    bundle_cap += f"\n🔗 {result.report_url.replace('.html', '.bundle.json')}"
                try:
                    if update is not None and update.message is not None:
                        with open(bundle_path, "rb") as bf:
                            await update.message.reply_document(
                                document=bf, filename=os.path.basename(bundle_path),
                                caption=bundle_cap,
                            )
                    elif self._app is not None:
                        with open(bundle_path, "rb") as bf:
                            await self._app.bot.send_document(
                                chat_id=chat_id, document=bf,
                                filename=os.path.basename(bundle_path), caption=bundle_cap,
                            )
                except Exception as e:
                    logger.warning("[telegram_bot] bundle send failed: %s", e)

            global _analysis_count
            _analysis_count += 1
            duration = f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"

            queue_info = f"\n📋 대기열: {len(self._queue)}건 남음" if self._queue else ""
            await send(f"✅ 분석 완료 (소요시간: {duration}초){queue_info}")

            # Send index page link as separate message
            if result.report_url and result.report_url.startswith("http"):
                base_url = result.report_url.rsplit("/", 1)[0]
                index_url = f"{base_url}/"
                await send(f"📁 전체 보고서 목록: {index_url}")

        except asyncio.CancelledError:
            # v3.4.2 — /stop /stopall 으로 취소됨. 사용자에게 알리고 정상 종료 시그널 전파.
            logger.info("[telegram_bot] Analysis cancelled by /stop or /stopall")
            try:
                await send("🛑 분석 중단됨")
            except Exception:
                pass
            raise

        except Exception as e:
            logger.exception("Analysis failed")
            await send(f"❌ 분석 실패: {str(e)[:200]}")

        finally:
            self._is_analyzing = False
            self._current_topic = ""
            self._current_task = None
            # Process next in queue (CancelledError 가 났어도 큐는 진행해야 함 — /stop 이면 큐 살아있음)
            await self._process_queue()

    def create_app(self) -> Application:
        """Create and configure the Telegram bot application."""
        app = (
            Application.builder()
            .token(self.config.telegram_bot_token)
            .post_init(self._on_app_post_init)
            .post_shutdown(self._on_app_post_shutdown)
            .build()
        )
        self._app = app

        app.add_handler(CommandHandler("start", self._start_command))
        app.add_handler(CommandHandler("status", self._status_command))
        app.add_handler(CommandHandler("stop", self._stop_command))           # v3.4.2
        app.add_handler(CommandHandler("stopall", self._stopall_command))     # v3.4.2
        app.add_handler(CommandHandler("queue", self._queue_command))
        app.add_handler(CommandHandler("reports", self._reports_command))
        app.add_handler(CommandHandler("analyze", self._analyze_command))
        app.add_handler(CommandHandler("bundle", self._bundle_command))        # v5.5.0
        # V3 Step 5-B (v2.9.5)
        app.add_handler(CommandHandler("watchlist", self._watchlist_command))
        app.add_handler(CommandHandler("fire", self._fire_command))
        # v5.1.0 — Daily Briefing
        app.add_handler(CommandHandler("briefing_on", self._briefing_on_command))
        app.add_handler(CommandHandler("briefing_off", self._briefing_off_command))
        app.add_handler(CommandHandler("briefing_status", self._briefing_status_command))
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._message_handler
            )
        )

        return app

    # ------------------------------------------------------------------
    # V3 Step 5-B (v2.9.5) — bot lifecycle hooks for watchlist monitor
    # ------------------------------------------------------------------

    async def _on_app_post_init(self, app: Application) -> None:
        """봇 시작 시 호출 — DB 에서 활성 신호 카운트 로깅 + monitor task 기동.

        Note: ``WatchlistRegistry`` 는 SQLite 영구 저장이라 *복구* 라는 액션이 별도로 필요하지
        않다. ``list_active()`` 호출 자체가 곧 부팅 시점의 활성 신호 스냅샷이며, monitor task 가
        주기적으로 다시 ``list_active()`` 를 호출한다. B 보강 ("WatchlistRegistry.load_active_signals
        패턴") 의 실질 구현.

        v5.1.0: Daily briefing scheduler task 도 함께 기동.
        """
        active_count = self.watchlist_registry.count_active()
        total_count = self.watchlist_registry.count_total()
        logger.info(
            "[telegram_bot] Watchlist boot: active=%d total=%d (DB=%s)",
            active_count, total_count, self.watchlist_registry.db_path,
        )
        # Monitor task 기동 — 별도 프로세스 없음, 봇 asyncio loop 안에서 도는 task.
        self._monitor_task = asyncio.create_task(
            run_monitor_loop(
                registry=self.watchlist_registry,
                notify_fn=self._notify_signal_fired,
                interval_seconds=3600,  # 1시간
            ),
            name="watchlist_monitor",
        )
        logger.info("[telegram_bot] Watchlist monitor task started")

        # v5.1.0 — Daily briefing scheduler task. enabled=False 라도 task 는 살아 있고
        # 트리거 시각에 단순 로깅만 — /briefing_on 구독은 항상 가능.
        sub_count = self.briefing_registry.count()
        logger.info(
            "[telegram_bot] Briefing boot: subscribers=%d enabled=%s time=%s tz=%s",
            sub_count, self.config.daily_briefing_enabled,
            self.config.daily_briefing_time, self.config.daily_briefing_tz,
        )
        self._briefing_task = asyncio.create_task(
            run_daily_briefing_loop(
                orchestrator=self.orchestrator,
                subscribers=self.briefing_registry,
                send_text_fn=self._send_text_to_chat,
                send_document_fn=self._send_document_to_chat,
                time_str=self.config.daily_briefing_time,
                tz_name=self.config.daily_briefing_tz,
                enabled=self.config.daily_briefing_enabled,
            ),
            name="daily_briefing_scheduler",
        )
        logger.info("[telegram_bot] Daily briefing scheduler task started")

    async def _on_app_post_shutdown(self, app: Application) -> None:
        """봇 종료 시 background task 정리. SQLite 데이터는 영구 보존."""
        for task_attr, task_label in (
            ("_monitor_task", "watchlist monitor"),
            ("_briefing_task", "daily briefing scheduler"),
        ):
            task = getattr(self, task_attr, None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(
                        "[telegram_bot] %s task shutdown error: %s", task_label, e,
                    )
                logger.info("[telegram_bot] %s task stopped", task_label)

    # ------------------------------------------------------------------
    # v5.1.0 — Send helpers used by the daily briefing scheduler
    # ------------------------------------------------------------------

    async def _send_text_to_chat(self, chat_id: int, text: str) -> None:
        """Send a text message to ``chat_id`` via the bot Application."""
        if self._app is None:
            logger.warning(
                "[telegram_bot] send_text called before app init; skipping (chat=%d)",
                chat_id,
            )
            return
        try:
            await self._app.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.warning(
                "[telegram_bot] send_message failed for chat=%d: %s", chat_id, e,
            )

    async def _send_document_to_chat(
        self, chat_id: int, file_path: str, caption: str,
    ) -> None:
        """Send a document attachment to ``chat_id`` via the bot Application."""
        if self._app is None:
            logger.warning(
                "[telegram_bot] send_document called before app init; skipping (chat=%d)",
                chat_id,
            )
            return
        try:
            with open(file_path, "rb") as f:
                await self._app.bot.send_document(
                    chat_id=chat_id, document=f,
                    filename=os.path.basename(file_path), caption=caption,
                )
        except Exception as e:
            logger.warning(
                "[telegram_bot] send_document failed for chat=%d: %s", chat_id, e,
            )
