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
            "Event Analysis Team\n\n"
            "Send me any event or situation to analyze.\n"
            "I will coordinate 7 AI agents to produce a comprehensive report.\n\n"
            "Commands:\n"
            "/analyze <event> -- Start analysis\n"
            "/start -- Show this message"
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
                "Usage: /analyze <event description>"
            )
            return

        await self._run_analysis(update, text)

    async def _message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle plain text messages as analysis requests."""
        if update.message is None or update.effective_chat is None:
            return

        if not self._is_authorized(update.effective_chat.id):
            return

        text = update.message.text
        if not text or not text.strip():
            return

        await self._run_analysis(update, text.strip())

    async def _run_analysis(self, update: Update, event_text: str) -> None:
        """Execute the analysis pipeline and send report."""
        if update.message is None or update.effective_chat is None:
            return

        chat_id = update.effective_chat.id
        msg = await update.message.reply_text(
            "\U0001f50d \ubd84\uc11d \uc2dc\uc791 \uc911..."
        )

        async def status_callback(status: str) -> None:
            try:
                await msg.edit_text(status)
            except Exception:
                pass

        try:
            result = await self.orchestrator.run_analysis(
                event_description=event_text,
                chat_id=chat_id,
                status_callback=status_callback,
            )

            # Send executive summary as text message
            summary_text = (
                f"\u2705 \ubd84\uc11d \uc644\ub8cc\n\n"
                f"\ud310\uc815: {result.audit_result.overall_verdict}\n"
                f"\uc18c\uc694\uc2dc\uac04: {result.total_duration_seconds:.1f}s\n\n"
                f"{result.executive_summary[:3000]}"
            )
            await update.message.reply_text(summary_text)

            # Send final report as HTML file
            report_dir = self.config.report_output_dir
            if os.path.isdir(report_dir):
                # Find the latest report
                reports = sorted(
                    [
                        f
                        for f in os.listdir(report_dir)
                        if f.endswith(".html")
                    ]
                )
                if reports:
                    report_path = os.path.join(report_dir, reports[-1])
                    with open(report_path, "rb") as f:
                        await update.message.reply_document(
                            document=f,
                            filename=os.path.basename(report_path),
                            caption="\U0001f4ca Full Analysis Report",
                        )

            await msg.edit_text("\u2705 \uc644\ub8cc! \ubcf4\uace0\uc11c\uac00 \uc804\uc1a1\ub418\uc5c8\uc2b5\ub2c8\ub2e4.")

        except Exception as e:
            logger.exception("Analysis failed")
            await msg.edit_text(f"\u274c \ubd84\uc11d \uc2e4\ud328: {str(e)[:200]}")

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
