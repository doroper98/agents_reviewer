"""Scenario Architect Agent -- ACT V+VI: scenarios and watch signals."""

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
    "당신은 시나리오 설계관. 사건의 향후 전개 경로를 설계하고, 각 시나리오로의 분기를 판별하는 신호를 식별함.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 반드시 4개 시나리오 (최선/기본/악화/최악)\n"
    "- 각 시나리오에 확률 배정\n"
    "- 각 시나리오가 핵심 행위자에게 미치는 영향 명시\n"
    "- 각 시나리오로 전환되는 트리거 신호 명시\n"
    "- 감시해야 할 핵심 지표 목록 제공\n"
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
    '  "base_case_summary": "기본 시나리오 요약 (2줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```"
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
    ) -> ScenarioAnalysis:
        """Design scenarios and watch signals based on all prior analyses."""
        context = {
            "context_analysis": context_analysis.model_dump(),
            "player_analysis": player_analysis.model_dump(),
            "dynamics_analysis": dynamics_analysis.model_dump(),
            "chain_reaction_analysis": chain_reaction_analysis.model_dump(),
        }
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ScenarioAnalysis)
