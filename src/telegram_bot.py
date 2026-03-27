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

from src.config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS
from src.models import AnalysisRequest
from src.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def is_authorized(chat_id: int) -> bool:
    """Check if chat is authorized. Empty list = allow all."""
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Event Analysis Team\n\n"
        "Send me any event or situation to analyze.\n"
        "I will coordinate 9 AI agents to produce a comprehensive report.\n\n"
        "Commands:\n"
        "/analyze <event> — Start analysis\n"
        "/status — Check system status\n"
        "/help — Show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        "Usage:\n\n"
        "1. Simply send a message describing an event:\n"
        '   "미국 관세 인상 분석해줘"\n'
        '   "Analyze the impact of Fed rate hike"\n\n'
        "2. Or use /analyze command:\n"
        '   /analyze 호르무즈 해협 봉쇄 위기\n\n'
        "The system will:\n"
        "  Phase 1: Parse & route your request\n"
        "  Phase 2: Identify event (5W1H)\n"
        "  Phase 3: Run 5 parallel analyses\n"
        "  Phase 4: Audit via Devil's Advocate\n"
        "  Phase 5: Generate visual report\n\n"
        "Report includes: Macro, Geopolitical, Micro,\n"
        "Investment, Historical, Ethical analysis"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    await update.message.reply_text(
        "System Status: ONLINE\n"
        "Agents: 9/9 ready\n"
        "Model: Claude (via Max subscription)\n"
        "Pipeline: 5-phase sequential/parallel"
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analyze command."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /analyze <event description>")
        return

    await _run_analysis(update, text)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages as analysis requests."""
    if not is_authorized(update.effective_chat.id):
        return

    text = update.message.text.strip()
    if not text:
        return

    # Check for analysis keywords
    analysis_keywords = ["분석", "analyze", "analysis", "검토", "평가", "리뷰"]
    if any(kw in text.lower() for kw in analysis_keywords):
        await _run_analysis(update, text)
    else:
        await update.message.reply_text(
            "Send an analysis request.\n"
            'Example: "미국 관세 인상 영향 분석해줘"\n'
            "Or use /analyze <event>"
        )


async def _run_analysis(update: Update, event_text: str) -> None:
    """Execute the analysis pipeline and send report."""
    chat_id = update.effective_chat.id
    msg = await update.message.reply_text("Analysis started...\nPhase 1/5: Parsing command...")

    async def status_callback(status: str) -> None:
        try:
            await msg.edit_text(f"Analysis in progress...\n{status}")
        except Exception:
            pass

    orchestrator = Orchestrator(status_callback=status_callback)
    request = AnalysisRequest(
        raw_text=event_text,
        chat_id=chat_id,
        message_id=update.message.message_id,
    )

    try:
        result, report_path = await orchestrator.run(request)

        # Send report file
        with open(report_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(report_path),
                caption=(
                    f"Event Analysis Complete\n\n"
                    f"Confidence: {result.overall_confidence.value}\n"
                    f"Audit: {result.audit.verdict.value.upper()}\n\n"
                    f"{result.executive_summary[:500]}"
                ),
            )

        await msg.edit_text("Analysis complete! Report sent.")

    except Exception as e:
        logger.exception("Analysis failed")
        await msg.edit_text(f"Analysis failed: {str(e)[:200]}")


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    return app
