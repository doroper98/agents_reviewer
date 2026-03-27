"""Event Identifier Agent -- Phase 2: 사건 식별 및 프로필 생성."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AnalysisRequest, EventProfile

SYSTEM_PROMPT = (
    "당신은 사건/이벤트 식별 전문가입니다. "
    "주어진 이벤트를 5W1H (Who, What, When, Where, Why, How) 프레임워크로 분석하고, "
    "사건의 정확한 정의와 범위를 설정합니다. "
    "출처의 신뢰도를 평가하고, 사건의 카테고리를 분류합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "event_name": "string",\n'
    '  "date": "string",\n'
    '  "location": "string",\n'
    '  "category": "string",\n'
    '  "who": "string",\n'
    '  "what": "string",\n'
    '  "when": "string",\n'
    '  "where": "string",\n'
    '  "why": "string",\n'
    '  "how": "string",\n'
    '  "sources": ["string"],\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class EventIdentifierAgent(BaseAgent):
    """Identifies and profiles events using the 5W1H framework."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="event_identifier",
            role="Event Identifier (사건 식별자)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, request: AnalysisRequest) -> EventProfile:
        """Analyze the event description and return an EventProfile."""
        context = {
            "event_description": request.event_description,
            "request_type": request.request_type,
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, EventProfile)
