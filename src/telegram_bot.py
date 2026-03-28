"""Telegram bot integration for the Event Analysis Team."""

from __future__ import annotations

import logging
import os

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


class TelegramBot:
    """Telegram bot that receives analysis commands and sends reports."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.orchestrator = Orchestrator(config)

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
            "5명의 AI 분석관이 종합 보고서를 작성합니다.\n\n"
            "명령어:\n"
            "/analyze <주제> — 분석 시작\n"
            "/start — 이 메시지 표시"
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

            # Send text report as code block
            text_report = self.orchestrator._build_text_report(result)
            # Split if too long for Telegram (4096 char limit)
            report_msg = f"```\n{text_report}\n```"
            if len(report_msg) > 4000:
                # Split into chunks
                chunks = [text_report[i:i+3900] for i in range(0, len(text_report), 3900)]
                for chunk in chunks:
                    await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")
            else:
                await update.message.reply_text(report_msg, parse_mode="Markdown")

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

            duration = f"{result.total_duration_seconds:.0f}" if result.total_duration_seconds else "?"
            await update.message.reply_text(
                f"✅ 분석 완료 (소요시간: {duration}초)"
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
        app.add_handler(CommandHandler("analyze", self._analyze_command))
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._message_handler
            )
        )

        return app
