"""Context Analyst Agent -- ACT I: situation board."""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AnalysisRequest, ContextAnalysis

SYSTEM_PROMPT = (
    "당신은 상황판 분석관. 사건의 팩트, 타임라인, 핵심 수치를 정리함.\n\n"
    "중요: 오늘 날짜는 {current_date}.\n"
    "반드시 최신 정보를 기반으로 분석할 것.\n"
    "웹 검색을 통해 최신 뉴스, 데이터, 현황을 확인한 후 분석.\n"
    "학습 데이터에만 의존하지 말 것.\n"
    "과거 정보를 현재로 혼동하지 말 것 (예: 이전 정부를 현 정부로 착각 금지).\n\n"
    "규칙:\n"
    "- 음슴체. 미사여구 금지\n"
    "- 검증된 팩트만. 추측 시 명시\n"
    "- 타임라인은 날짜+사건 형태\n"
    "- 핵심 수치는 구체적 숫자로\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "event_name": "사건명",\n'
    '  "event_name_en": "English name for report title",\n'
    '  "date": "YYYY-MM-DD",\n'
    '  "category": "분류",\n'
    '  "summary": "3줄 이내 핵심 요약",\n'
    '  "timeline": [{"date": "날짜", "event": "사건", "impact": "영향"}],\n'
    '  "key_figures": [{"label": "지표명", "value": "수치", "context": "맥락"}],\n'
    '  "background": "배경 설명 (5줄 이내)",\n'
    '  "sources": ["출처1", "출처2"],\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```"
)


class ContextAnalyst(BaseAgent):
    """Establishes facts, timeline, and key data points."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="context_analyst",
            role="Context Analyst (상황판 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, request: AnalysisRequest) -> ContextAnalysis:
        """Analyze event and return context / situation board."""
        context = {
            "event_description": request.event_description,
            "request_type": request.request_type,
        }
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        self.system_prompt = SYSTEM_PROMPT.format(current_date=context["current_date"])
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ContextAnalysis)
