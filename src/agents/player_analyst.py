"""Player Analyst Agent -- key actors identification.

DEPRECATED since v3.0.0. Use ``src.lenses.stakeholder_lens.StakeholderLens`` instead.
Legacy persona file is preserved (Anti-pattern #1 — 즉시 삭제 금지).
Removal scheduled for v4.0.0 (GOAL.md FUT-LEGACY-001).
"""

from __future__ import annotations

import warnings as _warnings
from datetime import datetime

_warnings.warn(
    "src.agents.player_analyst.PlayerAnalyst is deprecated since v3.0.0. "
    "Use src.lenses.stakeholder_lens.StakeholderLens instead. "
    "Legacy import path scheduled for removal in v4.0.0 (GOAL.md FUT-LEGACY-001).",
    DeprecationWarning,
    stacklevel=2,
)

from src.agents.base import BaseAgent
from src.config import Config
from src.models import ContextAnalysis, PlayerAnalysis

SYSTEM_PROMPT = (
    "당신은 최고의 이해관계자 분석가. 사건의 핵심 행위자들을 식별하고 각자의 입장, 자원, 전략을 분석함.\n"
    "입력에 strategic_directive가 있으면 그 지시에 따라 분석 관점과 기법을 조정할 것.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 용어 난이도: 대학교 학부생 수준. 어려운 한자어/외래어 대신 쉬운 우리말로\n"
    "  * 나쁜 예: '레버리지', '익스포저', '디스카운트', '헤지', '컨틴전시'\n"
    "  * 좋은 예: '지렛대(영향력)', '노출도', '할인(낮춤)', '위험 회피', '비상 대비책'\n"
    "- 전문 개념을 처음 쓸 땐 한 줄 설명 추가 (예: 모멘텀(흐름의 가속도))\n"
    "- 행위자는 국가, 기업, 인물, 기관, 시민 집단, 미디어 등 무엇이든 가능\n"
    "- 각 플레이어의 위험도/영향도를 극심|높음|보통|낮음으로 분류\n"
    "- 분석 시각을 다양하게 적용 (한 가지 틀에 갇히지 말 것):\n"
    "  * 자원/역량 관점 (보유 자산, 기술, 정보력, 동맹)\n"
    "  * 동기/이해관계 관점 (얻고자 하는 것, 두려워하는 것)\n"
    "  * 제약 관점 (법, 여론, 내부 정치, 시간 압박)\n"
    "  * 평판/정당성 관점 (도덕적 입지, 명분)\n"
    "  * 행동 패턴 관점 (과거 사례에서 드러난 성향)\n"
    "  * 비대칭 관점 (한쪽이 잃을 게 더 많은가)\n"
    "- 플레이어 간 관계(동맹/대립/중립/거래/감시 등) 명시\n"
    "- 숨은 행위자도 식별 (직접 보이지 않지만 영향을 주는 측)\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "players": [\n'
    "    {\n"
    '      "name": "이름",\n'
    '      "emoji": "🏢",\n'
    '      "role_tag": "역할 태그 (예: 게임 설정자, 도발자, 설계자, 축, 무임승차자, 가격수용자 등)",\n'
    '      "risk_level": "극심|높음|보통|낮음",\n'
    '      "position": "현재 입장/포지션 (2줄)",\n'
    '      "resources": "보유 자원/레버리지 (2줄)",\n'
    '      "strategy": "전략/게임플랜 (3줄)",\n'
    '      "vulnerability": "취약점 (1줄)",\n'
    '      "timeline_pressure": "시간 압박 정도와 임계점"\n'
    "    }\n"
    "  ],\n"
    '  "alliances": [{"group": ["A", "B"], "nature": "동맹|대립|경쟁|협력"}],\n'
    '  "power_dynamics": "전체 권력 역학 요약 (3줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```\n\n"
    "중요: 모든 필드는 선택적. 이 사건에 불필요한 필드는 빈 배열/빈 문자열로 두고, "
    "전략 지시에 따른 핵심 분석에 집중할 것."
)


class PlayerAnalyst(BaseAgent):
    """Identifies key actors/players, positions, resources, strategies."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="player_analyst",
            role="Player Analyst (플레이어 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=True,
        )

    async def analyze(self, context_analysis: ContextAnalysis, directive: str = "") -> PlayerAnalysis:
        """Analyze players based on context analysis."""
        context = {
            "context_analysis": context_analysis.model_dump(),
        }
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        if directive:
            context["strategic_directive"] = directive
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, PlayerAnalysis)
