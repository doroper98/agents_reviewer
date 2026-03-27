"""Data models for the event analysis system."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """User's analysis request."""

    event_description: str
    request_type: str = "full_analysis"
    requested_by: str = ""
    chat_id: int = 0


class ContextAnalysis(BaseModel):
    """ACT I: Context / situation board analysis."""

    event_name: str = ""
    event_name_en: str = ""
    date: str = ""
    category: str = ""
    summary: str = ""
    timeline: list[dict] = Field(default_factory=list)
    key_figures: list[dict] = Field(default_factory=list)
    background: str = ""
    sources: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class PlayerAnalysis(BaseModel):
    """ACT II: Player identification and strategy analysis."""

    players: list[dict] = Field(default_factory=list)
    alliances: list[dict] = Field(default_factory=list)
    power_dynamics: str = ""
    summary: str = ""
    confidence_score: float = 0.0


class DynamicsAnalysis(BaseModel):
    """ACT III: Structural dynamics and game theory analysis."""

    framework: str = ""
    core_tension: str = ""
    asymmetries: list[dict] = Field(default_factory=list)
    why_unresolved: str = ""
    tipping_points: list[dict] = Field(default_factory=list)
    key_insight: str = ""
    summary: str = ""
    confidence_score: float = 0.0


class ChainReactionAnalysis(BaseModel):
    """ACT IV: Cause-effect chain and domino effect analysis."""

    chain: list[dict] = Field(default_factory=list)
    break_points: list[dict] = Field(default_factory=list)
    worst_case: str = ""
    summary: str = ""
    confidence_score: float = 0.0


class ScenarioAnalysis(BaseModel):
    """ACT V+VI: Scenario design and watch signal identification."""

    scenarios: list[dict] = Field(default_factory=list)
    watch_signals: list[dict] = Field(default_factory=list)
    base_case_summary: str = ""
    summary: str = ""
    confidence_score: float = 0.0


class FullAnalysisResult(BaseModel):
    """Complete analysis result from all agents."""

    request: AnalysisRequest
    context: ContextAnalysis | None = None
    players: PlayerAnalysis | None = None
    dynamics: DynamicsAnalysis | None = None
    chain_reaction: ChainReactionAnalysis | None = None
    scenarios: ScenarioAnalysis | None = None
    executive_summary: str = ""
    report_url: str = ""
    report_path: str = ""
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    total_duration_seconds: float = 0.0
