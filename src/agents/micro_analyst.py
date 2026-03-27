"""Micro Analyst Agent -- 미시경제적 파급력 분석."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import EventProfile, MicroAnalysis

SYSTEM_PROMPT = (
    "당신은 미시경제 분석 전문가.\n\n"
    "출력 규칙:\n"
    "- 음슴체 (미사여구 금지)\n"
    "- 불릿 포인트 형태\n"
    "- 산업별/기업별 구체적 영향\n"
    "- 수치 데이터 우선\n"
    "- 출처 필수\n\n"
    "출력 예시:\n"
    "* 직격 산업 : 반도체, 자동차, 철강\n"
    "* 반도체 : TSMC 주가 -5%, 삼성전자 수출 제한 우려\n"
    "* 자동차 : 관세 25% 부과 시 미국 내 판매가 $3,000 상승\n"
    "* 공급망 : 중국산 부품 의존도 40% → 대체 소싱 6개월 소요\n"
    "* 소비자 : 전자제품 가격 10-15% 인상 예상\n"
    "* 요약 : {2-3줄 이내}\n"
    "* 출처 : {sources}\n\n"
    "반드시 JSON 형식으로 응답.\n\n"
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
