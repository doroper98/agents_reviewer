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
    model_name_light: str = "claude-sonnet-4-6"
    use_cli_mode: bool = True

    # V5 Phase 1A — ResearchDirector opt-in.
    # 켜져 있으면 orchestrator 가 Phase 1 (ContextAnalyst) 직후에 ResearchDirector
    # 를 호출해 AnalysisBrief 를 emit. 꺼져 있으면 design_via_heuristics 의
    # 결정적 fallback 만 사용 (LLM 0). v4.5.7 호출 경로의 byte-equal 보존을 위해
    # 디폴트 OFF. env: V5_RESEARCH_DIRECTOR=1 또는 .env 의 enable_research_director=true.
    enable_research_director: bool = False

    # V5 Phase 2 — VisualPlanner opt-in.
    # 켜져 있으면 Editor (Phase 1) 또는 composer 직후에 VisualPlanner 를 호출해
    # Vega-Lite spec 으로 exhibit list 를 emit. 꺼져 있으면 plan_via_heuristics
    # 가 v4.5.7 의 ComposedSection.charts 를 그대로 통과 (단 EvidenceDataset
    # Guard 는 적용 — Phase 2A). 디폴트 OFF — v4.5.7 byte-equal 보존.
    # env: V5_VISUAL_PLANNER=1.
    enable_visual_planner: bool = False

    # V5 Phase 7 — DeskEditor opt-in.
    # 켜져 있으면 Phase 7A (Deterministic Gate) 통과 후 DeskEditor (Opus 4.7
    # vision) 가 publish/hold/KILL 판정. 꺼져 있으면 v4.5.7 의 minimal fallback
    # 정책 그대로 ("어떻게든 발행"). 디폴트 OFF.
    # env: V5_DESK_EDITOR=1.
    enable_desk_editor: bool = False

    # V5 Phase 1 — Editor Pass opt-in.
    # 켜져 있으면 Composer (drafting) 직후 Editor (Opus 4.7) 가 7-rubric 으로
    # 비평·재집필. 꺼져 있으면 composer DraftReport 그대로 사용 (v4.5.7 byte-
    # equal). 디폴트 OFF. env: V5_EDITOR_PASS=1.
    enable_editor_pass: bool = False

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
