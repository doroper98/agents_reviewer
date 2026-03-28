"""Configuration for the Event Analysis Team system using Pydantic BaseSettings."""

from __future__ import annotations

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_project_name: str = "analysis-reports"
    report_output_dir: str = "reports"
    model_name: str = "claude-opus-4-6"
    use_cli_mode: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def allowed_chat_ids(self) -> list[int]:
        """Parse allowed chat IDs from ALLOWED_CHAT_IDS env var."""
        raw = os.getenv("ALLOWED_CHAT_IDS", "")
        if raw.strip():
            return [int(x.strip()) for x in raw.split(",") if x.strip()]
        return []

    @model_validator(mode="after")
    def _select_mode(self) -> "Config":
        """Auto-select API mode when an API key is provided."""
        if self.anthropic_api_key:
            self.use_cli_mode = False
        return self


def get_config() -> Config:
    """Create and return a Config instance."""
    return Config()
