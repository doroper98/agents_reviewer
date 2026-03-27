"""Data models for the event analysis system."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """User's analysis request."""

    event_description: str
    request_type: str = "full_analysis"
    requested_by: str = ""
    chat_id: int = 0


class EventProfile(BaseModel):
    """5W1H structured event profile."""

    event_name: str = ""
    date: str = ""
    location: str = ""
    category: str = ""
    who: str = ""
    what: str = ""
    when: str = ""
    where: str = ""
    why: str = ""
    how: str = ""
    sources: list[str] = Field(default_factory=list)
    confidence_score: float = 0.5


class MacroAnalysis(BaseModel):
    """Macroeconomic impact analysis."""

    gdp_impact: str = ""
    inflation_impact: str = ""
    trade_impact: str = ""
    monetary_policy_impact: str = ""
    labor_market_impact: str = ""
    key_indicators: list[dict] = Field(default_factory=list)
    summary: str = ""
    confidence_score: float = 0.5


class GeopoliticalAnalysis(BaseModel):
    """Geopolitical impact analysis."""

    affected_regions: list[str] = Field(default_factory=list)
    alliance_shifts: str = ""
    power_dynamics: str = ""
    conflict_risk_assessment: str = ""
    diplomatic_implications: str = ""
    sanctions_impact: str = ""
    summary: str = ""
    confidence_score: float = 0.5


class MicroAnalysis(BaseModel):
    """Microeconomic impact analysis."""

    affected_industries: list[str] = Field(default_factory=list)
    supply_chain_impact: str = ""
    consumer_behavior_impact: str = ""
    company_level_impacts: list[dict] = Field(default_factory=list)
    market_structure_changes: str = ""
    summary: str = ""
    confidence_score: float = 0.5


class InvestmentAnalysis(BaseModel):
    """Investment impact analysis."""

    asset_classes_affected: list[dict] = Field(default_factory=list)
    risk_assessment: str = ""
    short_term_outlook: str = ""
    medium_term_outlook: str = ""
    long_term_outlook: str = ""
    recommended_actions: list[str] = Field(default_factory=list)
    portfolio_impact: str = ""
    summary: str = ""
    confidence_score: float = 0.5


class HistoryEthicsAnalysis(BaseModel):
    """Historical parallels and ethical analysis."""

    historical_parallels: list[dict] = Field(default_factory=list)
    ethical_considerations: list[str] = Field(default_factory=list)
    moral_implications: str = ""
    lessons_learned: list[str] = Field(default_factory=list)
    societal_impact: str = ""
    cultural_significance: str = ""
    summary: str = ""
    confidence_score: float = 0.5


class AuditResult(BaseModel):
    """Devil's advocate audit result."""

    overall_verdict: Literal["PASS", "REVISE", "REJECT"] = "PASS"
    issues_found: list[dict] = Field(default_factory=list)
    agents_to_revise: list[str] = Field(default_factory=list)
    credibility_score: float = 0.5
    bias_detected: list[str] = Field(default_factory=list)
    logical_fallacies: list[str] = Field(default_factory=list)
    missing_perspectives: list[str] = Field(default_factory=list)
    summary: str = ""


class FullAnalysisResult(BaseModel):
    """Complete analysis result from all agents."""

    request: AnalysisRequest
    event_profile: EventProfile = Field(default_factory=EventProfile)
    macro_analysis: MacroAnalysis = Field(default_factory=MacroAnalysis)
    geopolitical_analysis: GeopoliticalAnalysis = Field(
        default_factory=GeopoliticalAnalysis
    )
    micro_analysis: MicroAnalysis = Field(default_factory=MicroAnalysis)
    investment_analysis: InvestmentAnalysis = Field(
        default_factory=InvestmentAnalysis
    )
    history_ethics_analysis: HistoryEthicsAnalysis = Field(
        default_factory=HistoryEthicsAnalysis
    )
    audit_result: AuditResult = Field(default_factory=AuditResult)
    executive_summary: str = ""
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    total_duration_seconds: float = 0.0
