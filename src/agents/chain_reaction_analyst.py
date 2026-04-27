"""Chain Reaction Analyst Agent -- cause-effect chains.

DEPRECATED since v3.0.0. Use ``src.lenses.cascade_lens.CascadeLens`` instead.
Legacy persona file is preserved (Anti-pattern #1 — 즉시 삭제 금지).
Removal scheduled for v4.0.0 (GOAL.md FUT-LEGACY-001).
"""

from __future__ import annotations

import warnings as _warnings
from datetime import datetime

_warnings.warn(
    "src.agents.chain_reaction_analyst.ChainReactionAnalyst is deprecated since v3.0.0. "
    "Use src.lenses.cascade_lens.CascadeLens instead. "
    "Legacy import path scheduled for removal in v4.0.0 (GOAL.md FUT-LEGACY-001).",
    DeprecationWarning,
    stacklevel=2,
)

from src.agents.base import BaseAgent
from src.config import Config
from src.models import (
    ChainReactionAnalysis,
    ContextAnalysis,
    DynamicsAnalysis,
    PlayerAnalysis,
)

SYSTEM_PROMPT = (
    "당신은 최고의 연쇄반응 분석가. 사건에서 비롯되는 인과 사슬과 파급효과를 추적함.\n"
    "입력에 strategic_directive가 있으면 그 지시에 따라 분석 관점과 추적 경로를 조정할 것.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 용어 난이도: 대학교 학부생 수준. 어려운 한자어/외래어 대신 쉬운 우리말로\n"
    "  * 나쁜 예: '파급', '파장', '연쇄적', '귀결', '촉발', '여파'\n"
    "  * 좋은 예: '번짐', '여운', '잇따라', '결과로 이어짐', '불러일으킴', '뒤이은 영향'\n"
    "- 영어 약어/전문용어 첫 등장 시 괄호로 풀어쓸 것\n"
    "- 각 단계가 다음 단계의 필수 전제조건이 되는 인과 사슬을 구성\n"
    "- 1차 효과(직접) → 2차 효과(연관 산업/시장) → 3차 효과(거시 환경/사회) 형태\n"
    "- 분석 시각을 사슬 단계별로 다양화:\n"
    "  * 의도된 효과 vs 의도하지 않은 부작용 구분\n"
    "  * 즉각 효과 vs 지연 효과 (시간차 명시)\n"
    "  * 선형 인과 vs 자기강화 루프 (작은 효과가 증폭되는 구조)\n"
    "  * 대칭 vs 비대칭 영향 (특정 집단에 집중되는지)\n"
    "  * 가시적 효과 vs 비가시적 효과 (드러나지 않지만 누적되는 변화)\n"
    "  * 가역적 vs 비가역적 변화 (되돌릴 수 있는가)\n"
    "- 각 단계에서 영향받는 영역/산업/국가/계층 명시\n"
    "- 각 단계에 시간 척도 표기 (즉시 / 수일 / 수주 / 수개월 / 수년)\n"
    "- 사슬이 끊어질 수 있는 조건도 명시 (정책 개입, 외부 충격, 행위자 선택)\n"
    "- 비선형/우발적 효과 가능성 별도 표기 (예측 어려운 흑조 사건)\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "chain": [\n'
    "    {\n"
    '      "step": 1,\n'
    '      "title": "단계명",\n'
    '      "description": "설명 (2줄)",\n'
    '      "affected": ["영향받는 대상들"],\n'
    '      "time_horizon": "즉시|수일|수주|수개월|수년",\n'
    '      "effect_type": "의도|부작용|증폭|지연",\n'
    '      "reversible": true,\n'
    '      "severity": "HIGH|MEDIUM|LOW"\n'
    "    }\n"
    "  ],\n"
    '  "feedback_loops": [\n'
    '    {"description": "사슬 안에서 자기강화/억제되는 구조"}\n'
    "  ],\n"
    '  "break_points": [\n'
    '    {"at_step": 2, "condition": "이 조건이 충족되면 사슬이 끊어짐"}\n'
    "  ],\n"
    '  "wildcards": [\n'
    '    {"event": "예측 어려운 흑조 사건", "probability": "낮음|중간"}\n'
    "  ],\n"
    '  "worst_case": "모든 사슬이 연결될 경우 최종 결과 (2줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```\n\n"
    "중요: 모든 필드는 선택적. 이 사건에 불필요한 필드는 빈 배열/빈 문자열로 두고, "
    "전략 지시에 따른 핵심 분석에 집중할 것."
)


class ChainReactionAnalyst(BaseAgent):
    """Traces cause-effect chains, domino effects, cascading impacts."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="chain_reaction_analyst",
            role="Chain Reaction Analyst (연쇄반응 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=True,
        )

    async def analyze(
        self,
        context_analysis: ContextAnalysis,
        player_analysis: PlayerAnalysis,
        dynamics_analysis: DynamicsAnalysis,
        directive: str = "",
    ) -> ChainReactionAnalysis:
        """Analyze cause-effect chains based on prior analyses."""
        context: dict = {}
        if context_analysis:
            context["context_analysis"] = context_analysis.model_dump()
        if player_analysis:
            context["player_analysis"] = player_analysis.model_dump()
        if dynamics_analysis:
            context["dynamics_analysis"] = dynamics_analysis.model_dump()
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        if directive:
            context["strategic_directive"] = directive
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ChainReactionAnalysis)
