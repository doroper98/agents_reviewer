"""Investment Analyst Agent -- 투자 영향 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import (
    EventProfile,
    GeopoliticalAnalysis,
    InvestmentAnalysis,
    MacroAnalysis,
    MicroAnalysis,
)

SYSTEM_PROMPT = (
    "당신은 투자 분석 전문가입니다. "
    "사건이 주식, 채권, 원자재, 외환, 암호화폐 등 자산군에 미치는 영향을 분석합니다. "
    "리스크 평가, 단기/중기/장기 전망, 포트폴리오 영향을 제공합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "asset_classes_affected": [{"asset_class": "string", "impact": "string", "direction": "string"}],\n'
    '  "risk_assessment": "string",\n'
    '  "short_term_outlook": "string",\n'
    '  "medium_term_outlook": "string",\n'
    '  "long_term_outlook": "string",\n'
    '  "recommended_actions": ["string"],\n'
    '  "portfolio_impact": "string",\n'
    '  "summary": "string",\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class InvestmentAnalyst(BaseAgent):
    """Analyzes investment impact of events across asset classes."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="investment_analyst",
            role="Investment Analyst (투자 분석가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(
        self,
        event_profile: EventProfile,
        macro: MacroAnalysis,
        geo: GeopoliticalAnalysis,
        micro: MicroAnalysis,
    ) -> InvestmentAnalysis:
        """Analyze investment impact using results from prior analyses."""
        context = {
            "event_profile": event_profile.model_dump(),
            "macro_analysis": macro.model_dump(),
            "geopolitical_analysis": geo.model_dump(),
            "micro_analysis": micro.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, InvestmentAnalysis)
