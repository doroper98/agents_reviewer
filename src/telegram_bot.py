"""Telegram bot integration for the Event Analysis Team."""

from __future__ import annotations

import logging
import os
import time
import glob
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
from src.models import WatchSignal
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
    """A queued analysis request."""
    event_text: str
    update: Update
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
            "/analyze <주제> — 분석 시작\n"
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

        # v4.1.0 — context + composer 모두 Opus 4.7 일관. 멀티 에이전트 7명은
        # 코드 보존하되 호출 안 됨. legacy 모델 라벨 (sonnet/opus 4.6) 은 의미 잃음.
        opus_47 = "claude-opus-4-7"

        agents_info = (
            f"📋 에이전트 구성 — Tier 4 (2-call 파이프라인)\n"
            f"  ① 상황 분석관 ······· {opus_47} · 사실/타임라인/출처 수집\n"
            f"  ② 편집장 (UnifiedComposer) · {opus_47} · 분석+보고서 단일 호출\n"
            f"\n"
            f"  ※ 모든 모드(fast/standard/deep) 가 동일하게 2회 LLM 호출.\n"
            f"     mode 는 편집장 prompt 의 분석 깊이 지시 (섹션 수 / 모순 명시 등) 만 결정.\n"
            f"     v4.1.0 — context 도 Opus 4.7 (이전 Sonnet 4.6 → 사실 품질 상향).\n"
            f"     legacy 7-agent 멀티 파이프라인은 호출 안 됨 (코드는 보존).\n"
        )

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
            f"{briefing_info}\n"
            f"\n{agents_info}"
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
                "분석을 실행하면 ScenarioArchitect 의 watch_signals 가 자동 등록됨."
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

    async def _notify_signal_fired(self, signal: WatchSignal) -> None:
        """Send signal-fired alert to ``signal.parent_chat_id`` via the bot Application."""
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
        try:
            await self._app.bot.send_message(chat_id=signal.parent_chat_id, text=text)
        except Exception as e:
            logger.warning(
                "[telegram_bot] send_message failed for chat=%d: %s",
                signal.parent_chat_id, e,
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

        await self._run_analysis(next_item.update, next_item.event_text)

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

    async def _run_analysis(self, update: Update, event_text: str) -> None:
        """Execute the analysis pipeline and send report."""
        if update.message is None or update.effective_chat is None:
            return

        self._is_analyzing = True
        self._current_topic = event_text
        # v3.4.2 — /stop /stopall 이 cancel() 호출할 수 있게 task 핸들 보관.
        self._current_task = asyncio.current_task()
        chat_id = update.effective_chat.id

        async def status_callback(status: str) -> None:
            """Send each status as a NEW message (not edit)."""
            try:
                await update.message.reply_text(status)
            except Exception:
                pass

        try:
            result = await self.orchestrator.run_analysis(
                event_description=event_text,
                chat_id=chat_id,
                status_callback=status_callback,
            )

            # Send text report (best effort — don't block report link)
            try:
                text_report = self.orchestrator._build_text_report(result)
                for i in range(0, len(text_report), 3900):
                    chunk = text_report[i:i+3900]
                    await update.message.reply_text(chunk)
            except Exception as e:
                logger.warning(f"Text report send failed: {e}")

            # Send glossary (best effort)
            try:
                glossary_text = self.orchestrator._build_glossary_text(result)
                if glossary_text:
                    for i in range(0, len(glossary_text), 3900):
                        chunk = glossary_text[i:i+3900]
                        await update.message.reply_text(chunk)
            except Exception as e:
                logger.warning(f"Glossary send failed: {e}")

            # Send report link (must always reach user)
            report_path = result.report_path
            if result.report_url and result.report_url.startswith("http"):
                md_url = result.report_url.replace(".html", ".md")
                await update.message.reply_text(
                    f"📊 Full Analysis Report\n\n"
                    f"🔗 보고서 링크: {result.report_url}\n"
                    f"🤖 AI 전달용 (Markdown): {md_url}"
                )
            elif report_path and os.path.isfile(report_path):
                # Fallback: send file only if Cloudflare upload failed
                with open(report_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=os.path.basename(report_path),
                        caption="📊 Full Analysis Report (외부링크 생성 실패 — 파일 첨부)",
                    )

            global _analysis_count
            _analysis_count += 1
            duration = f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"

            queue_info = f"\n📋 대기열: {len(self._queue)}건 남음" if self._queue else ""
            await update.message.reply_text(
                f"✅ 분석 완료 (소요시간: {duration}초){queue_info}"
            )

            # Send index page link as separate message
            if result.report_url and result.report_url.startswith("http"):
                base_url = result.report_url.rsplit("/", 1)[0]
                index_url = f"{base_url}/"
                await update.message.reply_text(
                    f"📁 전체 보고서 목록: {index_url}"
                )

        except asyncio.CancelledError:
            # v3.4.2 — /stop /stopall 으로 취소됨. 사용자에게 알리고 정상 종료 시그널 전파.
            logger.info("[telegram_bot] Analysis cancelled by /stop or /stopall")
            try:
                await update.message.reply_text("🛑 분석 중단됨")
            except Exception:
                pass
            raise

        except Exception as e:
            logger.exception("Analysis failed")
            await update.message.reply_text(f"❌ 분석 실패: {str(e)[:200]}")

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
