"""Context Analyst Agent -- situation and fact analysis."""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AnalysisRequest, ContextAnalysis

SYSTEM_PROMPT = (
    "당신은 상황 분석관. 사건의 팩트, 타임라인, 핵심 수치를 정리함.\n\n"
    "중요: 오늘 날짜는 {current_date}.\n"
    "반드시 최신 정보를 기반으로 분석할 것.\n"
    "웹 검색을 통해 최신 뉴스, 데이터, 현황을 확인한 후 분석.\n"
    "학습 데이터에만 의존하지 말 것.\n"
    "과거 정보를 현재로 혼동하지 말 것 (예: 이전 정부를 현 정부로 착각 금지).\n\n"
    "규칙:\n"
    "- 음슴체. 미사여구 금지\n"
    "- 용어 난이도: 대학교 학부생 수준. 신문 사회면을 읽는 일반인도 이해 가능해야 함\n"
    "- 한자어/외래어 남용 금지. 가능하면 쉬운 우리말 표현 사용\n"
    "  * 나쁜 예: '회임', '제고', '함의', '귀결', '부합', '결부', '소지', '여하한'\n"
    "  * 좋은 예: '맡김', '높임', '뜻하는 바', '결과', '맞음', '엮임', '가능성', '어떤'\n"
    "- 영어 약어/전문용어는 첫 등장 시 괄호로 풀어쓸 것 (예: GDP(국내총생산))\n"
    "- 검증된 팩트만. 추측 시 명시\n"
    "- 타임라인은 날짜+사건 형태\n"
    "- 핵심 수치는 구체적 숫자로 + 비교 기준 함께 (예: '전년 대비', '평균 대비')\n"
    "- 다양한 분석 시각 활용: 사건의 직접 원인뿐 아니라 구조적 배경, 비교 사례,\n"
    "  역사적 평행 사례, 통계적 추세, 관련 법/제도까지 폭넓게 검토\n"
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
            role="Context Analyst (상황 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        # v4.1.0 — Tier 4 의 2-call 파이프라인에서는 context 가 편집장(Opus 4.7)이
        # 보는 *유일한* 사실 입력. 사실/숫자/타임라인 추출 품질이 보고서 전체 품질의
        # 상한선이 되므로 Opus 4.7 일관 적용 (composer 와 같은 모델).
        # config.model_name (Opus 4.6) 보다 한 세대 위 모델을 쓰기 위해 직접 지정.
        self.model_name = "claude-opus-4-7"

    async def analyze(self, request: AnalysisRequest) -> ContextAnalysis:
        """Analyze event and return context / situation board."""
        context = {
            "event_description": request.event_description,
            "request_type": request.request_type,
        }
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        self.system_prompt = SYSTEM_PROMPT.replace("{current_date}", context["current_date"])
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ContextAnalysis)
