"""Micro Analyst Agent -- 미시경제적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, MicroAnalysis

SYSTEM_PROMPT = (
    "당신은 미시경제 분석 전문가입니다. "
    "사건이 특정 산업, 공급망, 소비자 행동, 개별 기업에 미치는 영향을 분석합니다. "
    "시장 구조 변화와 경쟁 환경 변화를 평가합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "affected_industries": ["string"],\n'
    '  "supply_chain_impact": "string",\n'
    '  "consumer_behavior_impact": "string",\n'
    '  "company_level_impacts": [{"company": "string", "impact": "string"}],\n'
    '  "market_structure_changes": "string",\n'
    '  "summary": "string",\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class MicroAnalyst(BaseAgent):
    """Analyzes microeconomic impact of events."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="micro_analyst",
            role="Micro Analyst (미시경제 분석가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, event_profile: EventProfile) -> MicroAnalysis:
        """Analyze microeconomic impact based on event profile."""
        context = {
            "event_profile": event_profile.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, MicroAnalysis)
