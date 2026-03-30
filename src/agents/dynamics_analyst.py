"""Dynamics Analyst Agent -- ACT III: structural dynamics analysis."""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import Config
from src.models import ContextAnalysis, DynamicsAnalysis, PlayerAnalysis

SYSTEM_PROMPT = (
    "당신은 구조 역학 분석관. 사건의 구조적 동인, 비대칭성, 게임이론적 측면을 분석함.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 비전문가도 이해할 수 있는 쉬운 표현 사용. 전문용어 쓸 경우 괄호 안에 간단한 설명 추가\n"
    "- 어떤 주제든 적용 가능한 프레임워크 사용 (게임이론, 시간 비대칭, 구조적 모순 등)\n"
    "- 왜 현 상황이 쉽게 해소되지 않는지 구조적 원인 분석\n"
    "- 각 행위자의 시계가 다르게 돌아가는 이유 설명\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "framework": "적용된 분석 프레임워크명",\n'
    '  "core_tension": "핵심 구조적 긴장 (2줄)",\n'
    '  "asymmetries": [\n'
    '    {"type": "비대칭 유형", "description": "설명", "advantage_to": "유리한 측"}\n'
    "  ],\n"
    '  "why_unresolved": "왜 쉽게 해결되지 않는가 (3줄)",\n'
    '  "tipping_points": [\n'
    '    {"condition": "전환 조건", "timeline": "예상 시점", "consequence": "결과"}\n'
    "  ],\n"
    '  "key_insight": "가장 중요한 통찰 1가지 (2줄)",\n'
    '  "summary": "핵심 요약",\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0\n'
    "}\n"
    "```"
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
    ) -> DynamicsAnalysis:
        """Analyze structural dynamics based on context and player analyses."""
        context = {
            "context_analysis": context_analysis.model_dump(),
            "player_analysis": player_analysis.model_dump(),
        }
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, DynamicsAnalysis)
