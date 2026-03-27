"""Configuration for the Event Analysis Team system."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_IDS: list[int] = [
    int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
]

CLAUDE_CODE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

# Model: claude-sonnet-4-6 for agents, can override per-agent
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
REPORT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

# Execution mode: "api" if ANTHROPIC_API_KEY is set, otherwise "claude_code"
EXECUTION_MODE = "api" if ANTHROPIC_API_KEY else "claude_code"
