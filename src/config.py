"""Configuration for the Event Analysis Team system using Pydantic BaseSettings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    allowed_chat_ids: list[int] = Field(default_factory=list)
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_project_name: str = "analysis-reports"
    report_output_dir: str = "reports"
    model_name: str = "claude-sonnet-4-6"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_nested_delimiter": "__",
    }

    @classmethod
    def _parse_allowed_chat_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, list):
            return v
        if isinstance(v, str) and v.strip():
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []


def get_config() -> Config:
    """Create and return a Config instance."""
    return Config()
