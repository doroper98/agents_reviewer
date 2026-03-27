"""Macro Analyst Agent -- 거시경제적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, MacroAnalysis

SYSTEM_PROMPT = (
    "당신은 거시경제 분석 전문가입니다. "
    "사건이 GDP, 인플레이션, 무역, 통화정책, 노동시장에 미치는 영향을 분석합니다. "
    "정량적 지표와 정성적 평가를 모두 제공하며, "
    "단기(1-3개월), 중기(3-12개월), 장기(1년+) 영향을 구분합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "gdp_impact": "string",\n'
    '  "inflation_impact": "string",\n'
    '  "trade_impact": "string",\n'
    '  "monetary_policy_impact": "string",\n'
    '  "labor_market_impact": "string",\n'
    '  "key_indicators": [{"name": "string", "direction": "string", "magnitude": "string"}],\n'
    '  "summary": "string",\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class MacroAnalyst(BaseAgent):
    """Analyzes macroeconomic impact of events."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="macro_analyst",
            role="Macro Analyst (거시경제 분석가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, event_profile: EventProfile) -> MacroAnalysis:
        """Analyze macroeconomic impact based on event profile."""
        context = {
            "event_profile": event_profile.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, MacroAnalysis)
