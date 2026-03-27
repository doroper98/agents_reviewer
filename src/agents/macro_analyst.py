"""Macro Analyst Agent -- 거시경제적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, MacroAnalysis

SYSTEM_PROMPT = (
    "당신은 거시경제 분석 전문가.\n\n"
    "출력 규칙:\n"
    "- 음슴체 사용 (미사여구 금지)\n"
    "- 불릿 포인트(*) 형태로 핵심 수치와 사실만\n"
    "- 정량적 데이터 우선 (%, 금액, 수치)\n"
    "- 출처 필수\n\n"
    "출력 예시:\n"
    "* GDP 영향 : -0.3%p (단기)\n"
    "* 인플레이션 : +0.5%p 상승 압력\n"
    "* 무역수지 : 대중 수출 15% 감소 예상\n"
    "* 통화정책 : 금리 동결 가능성 높음\n"
    "* 노동시장 : 제조업 일자리 2만개 감소 우려\n"
    "* 핵심 지표 : [리스트]\n"
    "* 요약 : {2-3줄 이내}\n"
    "* 출처 : {sources}\n\n"
    "반드시 JSON 형식으로 응답.\n\n"
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
