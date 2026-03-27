"""History & Ethics Analyst Agent -- 역사적 맥락 및 윤리적 판단."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, HistoryEthicsAnalysis

SYSTEM_PROMPT = (
    "당신은 역사학자이자 윤리학자입니다. "
    "사건의 역사적 유사 사례를 찾아 비교하고, 윤리적 함의를 분석합니다. "
    "과거의 교훈을 현재에 적용하며, 사회적/문화적 영향을 평가합니다. "
    "도덕적 판단의 근거를 명확히 제시합니다.\n\n"
    "## Output Schema\n"
    "Respond ONLY with valid JSON matching this schema:\n"
    "```json\n"
    "{\n"
    '  "historical_parallels": [{"event": "string", "year": "string", "similarity": "string", "outcome": "string"}],\n'
    '  "ethical_considerations": ["string"],\n'
    '  "moral_implications": "string",\n'
    '  "lessons_learned": ["string"],\n'
    '  "societal_impact": "string",\n'
    '  "cultural_significance": "string",\n'
    '  "summary": "string",\n'
    '  "confidence_score": 0.0-1.0\n'
    "}\n"
    "```"
)


class HistoryEthicsAnalyst(BaseAgent):
    """Analyzes historical parallels and ethical implications."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="history_ethics_analyst",
            role="History & Ethics Analyst (역사/윤리 분석가)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, event_profile: EventProfile) -> HistoryEthicsAnalysis:
        """Analyze historical parallels and ethical implications."""
        context = {
            "event_profile": event_profile.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, HistoryEthicsAnalysis)
