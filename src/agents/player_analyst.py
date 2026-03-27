"""Player Analyst Agent -- ACT II: key actors identification."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import ContextAnalysis, PlayerAnalysis

SYSTEM_PROMPT = (
    "당신은 플레이어 분석관. 사건의 핵심 행위자들을 식별하고 각자의 입장, 자원, 전략을 분석함.\n\n"
    "규칙:\n"
    "- 음슴체\n"
    "- 행위자는 국가, 기업, 인물, 기관 등 무엇이든 가능\n"
    "- 각 플레이어의 위험도/영향도를 EXTREME/HIGH/MODERATE/LOW로 분류\n"
    "- 플레이어 간 관계(동맹/대립/중립) 명시\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "players": [\n'
    "    {\n"
    '      "name": "이름",\n'
    '      "emoji": "🏢",\n'
    '      "role_tag": "역할 태그 (예: GAME SETTER, ARCHITECT, FULCRUM 등)",\n'
    '      "risk_level": "EXTREME|HIGH|MODERATE|LOW",\n'
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
    '  "confidence_score": 0.0\n'
    "}\n"
    "```"
)


class PlayerAnalyst(BaseAgent):
    """Identifies key actors/players, positions, resources, strategies."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="player_analyst",
            role="Player Analyst (플레이어 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

    async def analyze(self, context_analysis: ContextAnalysis) -> PlayerAnalysis:
        """Analyze players based on context analysis."""
        context = {
            "context_analysis": context_analysis.model_dump(),
        }
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, PlayerAnalysis)
