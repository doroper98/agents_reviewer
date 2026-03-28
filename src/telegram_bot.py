"""Telegram bot integration for the Event Analysis Team."""

from __future__ import annotations

import logging
import os
import time
import glob
import asyncio
import shutil

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

logger = logging.getLogger(__name__)

# Track bot start time and analysis count
_bot_start_time: float = 0.0
_analysis_count: int = 0


class TelegramBot:
    """Telegram bot that receives analysis commands and sends reports."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.orchestrator = Orchestrator(config)
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
            "/status — 서버 상태 확인\n"
            "? <질문> — 간단 질답\n"
            "/start — 이 메시지 표시"
        )

    async def _status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command — show bot health, uptime, token usage."""
        if update.message is None:
            return

        global _bot_start_time, _analysis_count

        # Uptime
        uptime_sec = time.time() - _bot_start_time if _bot_start_time else 0
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        uptime_str = f"{hours}시간 {minutes}분"

        # Report count
        report_dir = self.config.report_output_dir
        report_files = glob.glob(os.path.join(report_dir, "analysis_*.html")) if os.path.isdir(report_dir) else []
        report_count = len(report_files)

        # Memory usage
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            total = int([l for l in meminfo.split("\n") if "MemTotal" in l][0].split()[1])
            available = int([l for l in meminfo.split("\n") if "MemAvailable" in l][0].split()[1])
            mem_pct = int((1 - available / total) * 100)
            mem_str = f"{mem_pct}% 사용"
        except Exception:
            mem_str = "확인 불가"

        # Token usage via claude CLI
        token_info = ""
        try:
            claude_bin = shutil.which("claude")
            if claude_bin:
                proc = await asyncio.create_subprocess_exec(
                    claude_bin, "-p", "현재 토큰 사용량을 알려줘. 주간 한도 대비 몇% 사용했는지, 리셋 날짜가 언제인지 간결하게 답변.",
                    "--output-format", "text",
                    "--model", self.config.model_name,
                    "--dangerously-skip-permissions",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode == 0:
                    token_info = stdout.decode().strip().replace("**", "")
        except Exception:
            token_info = "토큰 정보 조회 실패"

        status_msg = (
            f"✅ 봇 실행 중\n\n"
            f"  가동시간: {uptime_str}\n"
            f"  생성된 보고서: {report_count}건\n"
            f"  이번 세션 분석: {_analysis_count}건\n"
            f"  모델: {self.config.model_name}\n"
            f"  서버 메모리: {mem_str}\n"
            f"\n토큰 사용량 확인:\n"
            f"  claude.ai → 설정 → 사용량"
        )

        await update.message.reply_text(status_msg)

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

        await self._run_analysis(update, text)

    async def _message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle plain text messages. ? prefix = quick question, otherwise = analysis."""
        if update.message is None or update.effective_chat is None:
            return

        if not self._is_authorized(update.effective_chat.id):
            return

        text = update.message.text
        if not text or not text.strip():
            return

        text = text.strip()

        # ? prefix = quick question mode
        if text.startswith("?"):
            question = text[1:].strip()
            if question:
                await self._quick_question(update, question)
                return

        await self._run_analysis(update, text)

    async def _quick_question(self, update: Update, question: str) -> None:
        """Answer a quick question directly via Claude CLI/API."""
        if update.message is None:
            return

        msg = await update.message.reply_text("💬 답변 준비 중...")

        try:
            import asyncio
            import shutil

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

            # Send text report (without glossary, for easy x.com sharing)
            text_report = self.orchestrator._build_text_report(result)
            if len(text_report) > 4000:
                chunks = [text_report[i:i+3900] for i in range(0, len(text_report), 3900)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(text_report)

            # Send glossary as a SEPARATE message
            glossary_text = self.orchestrator._build_glossary_text(result)
            if glossary_text:
                await update.message.reply_text(glossary_text)

            # Send HTML file with share link in caption
            report_path = result.report_path
            if report_path and os.path.isfile(report_path):
                caption = "📊 Full Analysis Report"
                if result.report_url and result.report_url.startswith("http"):
                    caption += f"\n\n공유 링크: {result.report_url}"
                with open(report_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=os.path.basename(report_path),
                        caption=caption,
                    )

            global _analysis_count
            _analysis_count += 1
            duration = f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"
            await update.message.reply_text(
                f"✅ 분석 완료 (소요시간: {duration}초)"
            )

            # Send index page link as separate message
            if result.report_url and result.report_url.startswith("http"):
                base_url = result.report_url.rsplit("/", 1)[0]
                index_url = f"{base_url}/"
                await update.message.reply_text(
                    f"📁 전체 보고서 목록: {index_url}"
                )

        except Exception as e:
            logger.exception("Analysis failed")
            await update.message.reply_text(f"❌ 분석 실패: {str(e)[:200]}")

    def create_app(self) -> Application:
        """Create and configure the Telegram bot application."""
        app = (
            Application.builder()
            .token(self.config.telegram_bot_token)
            .build()
        )

        app.add_handler(CommandHandler("start", self._start_command))
        app.add_handler(CommandHandler("status", self._status_command))
        app.add_handler(CommandHandler("analyze", self._analyze_command))
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._message_handler
            )
        )

        return app
