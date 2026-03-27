"""Data models for the event analysis system."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnalysisPhase(str, Enum):
    IDENTIFICATION = "identification"
    PARALLEL_ANALYSIS = "parallel_analysis"
    AUDIT = "audit"
    SYNTHESIS = "synthesis"


class AuditVerdict(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    REJECT = "reject"


class ConfidenceGrade(str, Enum):
    A = "A"  # High confidence
    B = "B"  # Moderate confidence
    C = "C"  # Low confidence
    D = "D"  # Very low confidence


class ImpactLevel(int, Enum):
    MINIMAL = 1
    LOW = 2
    MODERATE = 3
    HIGH = 4
    CRITICAL = 5


class EventProfile(BaseModel):
    """5W1H structured event profile."""
    who: str = ""
    what: str = ""
    when: str = ""
    where: str = ""
    why: str = ""
    how: str = ""
    key_data_points: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: ConfidenceGrade = ConfidenceGrade.C


class MacroAnalysis(BaseModel):
    gdp_impact: str = ""
    monetary_policy_impact: str = ""
    inflation_impact: str = ""
    trade_fx_impact: str = ""
    fiscal_policy_impact: str = ""
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    summary: str = ""


class GeopoliticalAnalysis(BaseModel):
    relations_impact: str = ""
    sanctions_trade_risk: str = ""
    military_security_risk: str = ""
    energy_supply_chain_impact: str = ""
    regional_stability: str = ""
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    summary: str = ""


class MicroAnalysis(BaseModel):
    affected_sectors: list[str] = Field(default_factory=list)
    company_impact: str = ""
    consumer_behavior: str = ""
    supply_chain_pricing: str = ""
    competitive_landscape: str = ""
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    summary: str = ""


class InvestmentAnalysis(BaseModel):
    equities_impact: str = ""
    bonds_impact: str = ""
    commodities_impact: str = ""
    crypto_impact: str = ""
    real_estate_impact: str = ""
    sector_rotation: str = ""
    hedge_strategy: str = ""
    short_term_outlook: str = ""
    mid_term_outlook: str = ""
    long_term_outlook: str = ""
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    summary: str = ""


class HistoricalCase(BaseModel):
    event_name: str = ""
    year: str = ""
    similarities: str = ""
    differences: str = ""
    outcome: str = ""


class EthicalAnalysis(BaseModel):
    utilitarian_view: str = ""
    deontological_view: str = ""
    virtue_ethics_view: str = ""
    social_justice_view: str = ""
    summary: str = ""


class HistoryEthicsAnalysis(BaseModel):
    historical_cases: list[HistoricalCase] = Field(default_factory=list)
    pattern_analysis: str = ""
    ethical_analysis: EthicalAnalysis = Field(default_factory=EthicalAnalysis)
    summary: str = ""


class AuditResult(BaseModel):
    logical_consistency: str = ""
    biases_detected: list[str] = Field(default_factory=list)
    data_quality_grade: ConfidenceGrade = ConfidenceGrade.C
    counter_scenarios: list[str] = Field(default_factory=list)
    cross_validation_issues: list[str] = Field(default_factory=list)
    verdict: AuditVerdict = AuditVerdict.PASS
    revision_requests: list[str] = Field(default_factory=list)
    summary: str = ""


class AnalysisRequest(BaseModel):
    """User's analysis request."""
    raw_text: str
    chat_id: int
    message_id: int


class FullAnalysisResult(BaseModel):
    """Complete analysis result from all agents."""
    request: AnalysisRequest
    event_profile: EventProfile = Field(default_factory=EventProfile)
    macro: MacroAnalysis = Field(default_factory=MacroAnalysis)
    geopolitical: GeopoliticalAnalysis = Field(default_factory=GeopoliticalAnalysis)
    micro: MicroAnalysis = Field(default_factory=MicroAnalysis)
    investment: InvestmentAnalysis = Field(default_factory=InvestmentAnalysis)
    history_ethics: HistoryEthicsAnalysis = Field(default_factory=HistoryEthicsAnalysis)
    audit: AuditResult = Field(default_factory=AuditResult)
    overall_confidence: ConfidenceGrade = ConfidenceGrade.C
    executive_summary: str = ""
