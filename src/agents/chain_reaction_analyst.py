"""Chain Reaction Analyst Agent -- ACT IV: cause-effect chains."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import (
    ChainReactionAnalysis,
    ContextAnalysis,
    DynamicsAnalysis,
    PlayerAnalysis,
)

SYSTEM_PROMPT = (
    "당신은 연쇄반응 분석관. 사건에서 비롯되는 인과 사슬과 도미노 효과를 추적함.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 각 단계가 다음 단계의 필수 전제조건이 되는 인과 사슬을 구성\n"
    "- 1차 효과 → 2차 효과 → 3차 효과... 형태\n"
    "- 각 단계에서 영향받는 영역/산업/국가 명시\n"
    "- 사슬이 끊어질 수 있는 조건도 명시\n"
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
    '      "severity": "HIGH|MEDIUM|LOW"\n'
    "    }\n"
    "  ],\n"
    '  "break_points": [\n'
    '    {"at_step": 2, "condition": "이 조건이 충족되면 사슬이 끊어짐"}\n'
    "  ],\n"
    '  "worst_case": "모든 사슬이 연결될 경우 최종 결과 (2줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```"
)


class ChainReactionAnalyst(BaseAgent):
    """Traces cause-effect chains, domino effects, cascading impacts."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="chain_reaction_analyst",
            role="Chain Reaction Analyst (연쇄반응 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(
        self,
        context_analysis: ContextAnalysis,
        player_analysis: PlayerAnalysis,
        dynamics_analysis: DynamicsAnalysis,
    ) -> ChainReactionAnalysis:
        """Analyze cause-effect chains based on prior analyses."""
        context = {
            "context_analysis": context_analysis.model_dump(),
            "player_analysis": player_analysis.model_dump(),
            "dynamics_analysis": dynamics_analysis.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ChainReactionAnalysis)
