"""Dynamics Analyst Agent -- structural dynamics analysis.

DEPRECATED since v3.0.0. Use ``src.lenses.structural_lens.StructuralLens`` instead.
Legacy persona file is preserved (Anti-pattern #1 — 즉시 삭제 금지).
Removal scheduled for v4.0.0 (GOAL.md FUT-LEGACY-001).
"""

from __future__ import annotations

import warnings as _warnings
from datetime import datetime

_warnings.warn(
    "src.agents.dynamics_analyst.DynamicsAnalyst is deprecated since v3.0.0. "
    "Use src.lenses.structural_lens.StructuralLens instead. "
    "Legacy import path scheduled for removal in v4.0.0 (GOAL.md FUT-LEGACY-001).",
    DeprecationWarning,
    stacklevel=2,
)

from src.agents.base import BaseAgent
from src.config import Config
from src.models import ContextAnalysis, DynamicsAnalysis, PlayerAnalysis

SYSTEM_PROMPT = (
    "당신은 최고의 구조 분석가. 사건의 이면에 있는 구조적 원인과 힘의 역학을 분석함.\n"
    "입력에 strategic_directive가 있으면 그 지시에 따라 분석 관점과 기법을 조정할 것.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 용어 난이도: 대학교 학부생 수준. 학술 용어는 풀어서 설명\n"
    "  * 나쁜 예: '내생적', '외생적', '항상성', '경로의존', '귀납적', '연역적'\n"
    "  * 좋은 예: '내부에서 생긴', '외부에서 온', '균형 유지', '한 번 정해진 길을 따라감',\n"
    "    '사례에서 일반화', '원리에서 도출'\n"
    "- 영어 약어/외래어는 첫 등장 시 괄호로 풀어쓸 것\n"
    "- 사건의 성격에 맞는 분석 방식을 2~3개 이상 자유롭게 조합 (단일 틀에 갇히지 말 것)\n"
    "- 적용 가능한 분석 시각 풀(자유 선택, 조합 가능):\n"
    "  * 게임이론 (죄수의 딜레마, 치킨게임, 협상 균형)\n"
    "  * 시스템 사고 (피드백 루프, 자기강화 동학, 균형 메커니즘)\n"
    "  * 인과 분석 (1차/2차/3차 원인, 근본 원인 vs 촉발 원인)\n"
    "  * 권력/자원 비대칭 분석 (정보, 자본, 시간, 정당성의 격차)\n"
    "  * 신호 이론 (의도 신호, 허세 vs 진심 구분)\n"
    "  * 경로 의존성 (과거 선택이 현재를 어떻게 가두었나)\n"
    "  * 비교 사례 분석 (유사 사건의 전개와 결과)\n"
    "  * 역사적 평행 사례 (다른 시대/지역의 비슷한 구조)\n"
    "  * 정치경제적 관점 (이익집단, 분배 갈등, 제도 설계)\n"
    "  * 행동경제학 관점 (인지 편향, 손실 회피, 닻 효과)\n"
    "  * 네트워크 분석 (중심성, 약한 고리, 매개자)\n"
    "  * 임계점/티핑포인트 동학 (작은 변화가 큰 결과로 증폭되는 지점)\n"
    "  * 인지편향 점검 (확증편향, 정상화편향, 가용성편향이 분석에 끼친 영향)\n"
    "  * 적대적 관점 (Red Team, 반대 가설로 점검)\n"
    "- 적용한 분석 시각의 이름과 그렇게 본 이유를 framework 필드에 간략히 기재\n"
    "- 왜 현 상황이 쉽게 해소되지 않는지 근본 원인 분석 (구조/제도/인센티브 차원)\n"
    "- 각 행위자 간 힘의 불균형이 있다면 설명 (없으면 생략)\n"
    "- 가능하면 반대 가설/대안 해석 한 가지 함께 제시 (counter_view 필드 활용)\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "framework": "분석에 사용한 관점들 (예: \'게임이론 + 경로 의존성 + 행동경제학\')",\n'
    '  "core_tension": "이 사건의 핵심 갈등/긴장 구조 (2줄)",\n'
    '  "asymmetries": [\n'
    '    {"type": "불균형 유형", "description": "설명", "advantage_to": "유리한 측"}\n'
    "  ],\n"
    '  "feedback_loops": [\n'
    '    {"type": "강화|균형", "description": "어떤 변수가 어떻게 자기 자신을 키우거나 누르는지"}\n'
    "  ],\n"
    '  "why_unresolved": "왜 쉽게 해결되지 않는가 (3줄)",\n'
    '  "tipping_points": [\n'
    '    {"condition": "전환 조건", "timeline": "예상 시점", "consequence": "결과"}\n'
    "  ],\n"
    '  "counter_view": "반대 가설 또는 대안 해석 한 가지 (2줄, 없으면 빈 문자열)",\n'
    '  "cognitive_biases": ["분석 시 경계해야 할 인지 편향 (예: 확증편향, 정상화편향)"],\n'
    '  "key_insight": "가장 중요한 통찰 1가지 (2줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```\n\n"
    "중요: 모든 필드는 선택적. 이 사건에 불필요한 필드는 빈 배열/빈 문자열로 두고, "
    "전략 지시에 따른 핵심 분석에 집중할 것. 억지로 채우지 말 것."
)


class DynamicsAnalyst(BaseAgent):
    """Analyzes structural dynamics, asymmetries, game theory aspects."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="dynamics_analyst",
            role="Dynamics Analyst (구조 역학 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(
        self,
        context_analysis: ContextAnalysis,
        player_analysis: PlayerAnalysis,
        directive: str = "",
    ) -> DynamicsAnalysis:
        """Analyze structural dynamics based on context and player analyses."""
        context: dict = {}
        if context_analysis:
            context["context_analysis"] = context_analysis.model_dump()
        if player_analysis:
            context["player_analysis"] = player_analysis.model_dump()
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        if directive:
            context["strategic_directive"] = directive
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, DynamicsAnalysis)
