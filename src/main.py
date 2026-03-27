"""Entry point for the Event Analysis Team system."""

from __future__ import annotations

import logging

from src.telegram_bot import create_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the Telegram bot."""
    logger.info("Starting Event Analysis Team...")
    app = create_bot()
    logger.info("Bot is running. Waiting for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
