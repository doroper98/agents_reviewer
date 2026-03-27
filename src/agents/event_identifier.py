"""Event Identifier Agent -- Phase 2: 사건 식별 및 프로필 생성."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AnalysisRequest, EventProfile

SYSTEM_PROMPT = (
    "당신은 사건/이벤트 식별 전문가.\n\n"
    "출력 규칙:\n"
    "- 음슴체 사용 (미사여구 금지, 짧고 직관적인 문장만)\n"
    "- 불릿 포인트(*) 형태로 핵심 사실만 나열\n"
    "- 모든 항목에 출처 명시\n"
    "- 줄글 금지, 문장형 서술 금지\n\n"
    "출력 형식:\n"
    "* 사건명 : {사건명}\n"
    "* 일시 : {when}\n"
    "* 장소 : {where}\n"
    "* 주체 : {who}\n"
    "* 내용 : {what}\n"
    "* 원인 : {why}\n"
    "* 경과 : {how}\n"
    "* 출처 : {sources}\n"
    "* 카테고리 : {category}\n"
    "* 신뢰도 : {0.0~1.0}\n\n"
    "반드시 JSON 형식으로 응답.\n\n"
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
