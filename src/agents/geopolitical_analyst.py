"""Geopolitical Analyst Agent -- 지정학적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, GeopoliticalAnalysis

SYSTEM_PROMPT = (
    "당신은 지정학 분석 전문가.\n\n"
    "출력 규칙:\n"
    "- 음슴체 (미사여구 금지)\n"
    "- 불릿 포인트 형태\n"
    "- 지역별 영향 구분\n"
    "- 출처 필수\n\n"
    "출력 예시:\n"
    "* 영향 지역 : 동아시아, 유럽, 중동\n"
    "* 동맹 변화 : 한미동맹 강화, 중러 밀착\n"
    "* 권력 역학 : 미국 단극체제 약화\n"
    "* 분쟁 위험 : 대만해협 긴장 고조 (위험도 7/10)\n"
    "* 외교 함의 : G7 공동성명 예상\n"
    "* 제재 영향 : 대러 제재 강화 가능\n"
    "* 요약 : {2-3줄 이내}\n"
    "* 출처 : {sources}\n\n"
    "반드시 JSON 형식으로 응답.\n\n"
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
