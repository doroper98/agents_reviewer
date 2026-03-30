"""Dynamics Analyst Agent -- ACT III: structural dynamics analysis."""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.config import Config
from src.models import ContextAnalysis, DynamicsAnalysis, PlayerAnalysis

SYSTEM_PROMPT = (
    "당신은 구조 분석관. 사건의 이면에 있는 구조적 원인과 힘의 역학을 분석함.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 비전문가도 이해할 수 있는 쉬운 표현 사용. 전문용어 쓸 경우 괄호 안에 간단한 설명 추가\n"
    "- 사건의 성격에 맞는 분석 방식을 자유롭게 선택 (특정 프레임워크 강제 금지)\n"
    "- 왜 현 상황이 쉽게 해소되지 않는지 근본 원인 분석\n"
    "- 각 행위자 간 힘의 불균형이 있다면 설명 (없으면 생략)\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "framework": "분석에 사용한 관점 (자유 기술)",\n'
    '  "core_tension": "이 사건의 핵심 갈등/긴장 구조 (2줄)",\n'
    '  "asymmetries": [\n'
    '    {"type": "불균형 유형", "description": "설명", "advantage_to": "유리한 측"}\n'
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
    "```\n\n"
    "참고: asymmetries는 실제로 불균형이 있을 때만 채울 것. 억지로 만들지 말 것."
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
