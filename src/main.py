"""Entry point for the Event Analysis Team system."""

from __future__ import annotations

import logging
import signal
import sys

from src.config import get_config
from src.telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Load config, initialize orchestrator, start Telegram bot."""
    config = get_config()

    if not config.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    if not config.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is not set. API calls will fail."
        )

    bot = TelegramBot(config)
    app = bot.create_app()

    # Graceful shutdown
    def handle_signal(signum: int, frame: object) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Starting Event Analysis Team bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
