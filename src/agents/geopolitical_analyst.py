"""Geopolitical Analyst Agent -- 지정학적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, GeopoliticalAnalysis

SYSTEM_PROMPT = (
    "당신은 지정학 분석 전문가입니다. "
    "사건이 국제 관계, 동맹 구조, 권력 역학, 분쟁 위험, 외교적 함의에 미치는 영향을 분석합니다. "
    "지역별 파급력을 평가하고 제재/규제 변화 가능성을 예측합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "affected_regions": ["string"],\n'
    '  "alliance_shifts": "string",\n'
    '  "power_dynamics": "string",\n'
    '  "conflict_risk_assessment": "string",\n'
    '  "diplomatic_implications": "string",\n'
    '  "sanctions_impact": "string",\n'
    '  "summary": "string",\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class GeopoliticalAnalyst(BaseAgent):
    """Analyzes geopolitical impact of events."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="geopolitical_analyst",
            role="Geopolitical Analyst (지정학 분석가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, event_profile: EventProfile) -> GeopoliticalAnalysis:
        """Analyze geopolitical impact based on event profile."""
        context = {
            "event_profile": event_profile.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, GeopoliticalAnalysis)
