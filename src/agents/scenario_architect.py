"""Scenario Architect Agent -- scenarios and watch signals."""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import Config
from src.models import (
    ChainReactionAnalysis,
    ContextAnalysis,
    DynamicsAnalysis,
    PlayerAnalysis,
    ScenarioAnalysis,
)

SYSTEM_PROMPT = (
    "당신은 최고의 시나리오 설계가. 사건의 향후 전개 경로를 설계하고, 각 시나리오로의 분기를 판별하는 신호를 식별함.\n"
    "입력에 strategic_directive가 있으면 그 지시에 따라 시나리오 설계 방향을 조정할 것.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 용어 난이도: 대학교 학부생 수준. 어려운 한자어/영어 용어 대신 쉬운 우리말로\n"
    "  * 나쁜 예: '베이스라인', '컨센서스', '내러티브', '바이어스', '디스럽션'\n"
    "  * 좋은 예: '기본 흐름', '대체적 합의', '서사/이야기 흐름', '치우침', '큰 변화'\n"
    "- 영어 약어/외래어 첫 등장 시 괄호로 풀어쓸 것\n"
    "- 시나리오 개수와 유형은 사건 성격에 맞게 자유 결정 (2~5개)\n"
    "- 시나리오 설계에 다양한 방법론 활용 (단순 좋음/나쁨이 아니라):\n"
    "  * 결정 변수 기반 (핵심 변수 2개 조합으로 4사분면 시나리오)\n"
    "  * 추세 연장 vs 추세 단절 (현재 흐름 유지 / 갑자기 꺾임)\n"
    "  * 행위자 선택 분기 (어느 측이 어떤 결정을 내리느냐)\n"
    "  * 외부 충격 시나리오 (예측 어려운 외부 변수가 끼어들 때)\n"
    "  * 시간 척도 분기 (단기/중기/장기에 따라 다른 결과)\n"
    "  * 베이지안 업데이트 (새 정보가 들어올 때 확률이 어떻게 바뀌는가)\n"
    "- 각 시나리오에 확률 배정 (모든 확률 합 = 100%)\n"
    "- 각 시나리오에 '필요 전제조건' 명시 (이 시나리오가 성립하려면 무엇이 참이어야 하는가)\n"
    "- 각 시나리오가 핵심 행위자에게 미치는 영향 명시\n"
    "- 각 시나리오로 전환되는 트리거 신호 명시\n"
    "- 감시해야 할 핵심 지표 목록 제공 (선행 신호 우선)\n"
    "- 핵심 가정의 무효화 조건 명시 (이런 일이 생기면 분석 자체를 다시 해야 함)\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "id": 1,\n'
    '      "name": "시나리오명",\n'
    '      "tag": "짧은 태그 (예: 최선, 기본선, 악화, 최악)",\n'
    '      "probability": "확률 (예: 25%)",\n'
    '      "description": "전개 경로 (3줄)",\n'
    '      "preconditions": ["이 시나리오 성립에 필요한 전제 1", "전제 2"],\n'
    '      "trigger": "이 시나리오로 전환되는 신호",\n'
    '      "impact_by_player": [\n'
    '        {"player": "행위자명", "impact": "영향 (1줄)", "sentiment": "positive|negative|neutral"}\n'
    "      ]\n"
    "    }\n"
    "  ],\n"
    '  "watch_signals": [\n'
    "    {\n"
    '      "signal": "감시 신호명",\n'
    '      "description": "설명 (1줄)",\n'
    '      "indicates": "이 신호가 가리키는 시나리오",\n'
    '      "icon": "이모지"\n'
    "    }\n"
    "  ],\n"
    '  "invalidation_conditions": ["분석을 다시 해야 하는 조건 1", "조건 2"],\n'
    '  "base_case_summary": "기본 시나리오 요약 (2줄)",\n'
    '  "summary": "균형 분석 본문. 반드시 아래 4개 단락으로 구성하고, '
    '단락 사이는 빈 줄(\\n\\n)로 구분할 것:\\n\\n'
    "[1단락] 핵심 판단: 가장 가능성 높은 흐름과 그 근거 2~3개.\\n\\n"
    "[2단락] 상방/하방 비대칭: 잘 풀릴 때의 상한과 잘못될 때의 하한, "
    "그리고 어느 쪽이 더 무거운지.\\n\\n"
    "[3단락] 변수 민감도: 어떤 변수가 결과를 가장 크게 바꾸는지 우선순위.\\n\\n"
    "[4단락] 분석가의 한계와 유보: 무엇을 모르고 있고 어떤 가정에 의존하는지. "
    '각 단락은 3~4문장 이내로 간결하게.",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```\n\n"
    "중요: 모든 필드는 선택적. 이 사건에 불필요한 필드는 빈 배열/빈 문자열로 두고, "
    "전략 지시에 따른 핵심 분석에 집중할 것."
)


class ScenarioArchitect(BaseAgent):
    """Designs branching scenarios and identifies watch signals."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="scenario_architect",
            role="Scenario Architect (시나리오 설계관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(
        self,
        context_analysis: ContextAnalysis,
        player_analysis: PlayerAnalysis,
        dynamics_analysis: DynamicsAnalysis,
        chain_reaction_analysis: ChainReactionAnalysis,
        directive: str = "",
    ) -> ScenarioAnalysis:
        """Design scenarios and watch signals based on all prior analyses.

        v3.1.0: persona 단계가 없는 fast/standard 에서는 player/dynamics/chain_reaction
        이 None 으로 들어옴 — context 만 사용.
        """
        context: dict = {}
        if context_analysis:
            context["context_analysis"] = context_analysis.model_dump()
        # v3.1.0: persona 데이터가 None 이 아닐 때만 동봉 (fast/standard 토큰 절약).
        if player_analysis is not None:
            context["player_analysis"] = player_analysis.model_dump()
        if dynamics_analysis is not None:
            context["dynamics_analysis"] = dynamics_analysis.model_dump()
        if chain_reaction_analysis is not None:
            context["chain_reaction_analysis"] = chain_reaction_analysis.model_dump()
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        if directive:
            context["strategic_directive"] = directive
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ScenarioAnalysis)
