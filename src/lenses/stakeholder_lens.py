"""Stakeholder lens — 이해관계자 식별·전략·위험도. 페르소나 PlayerAnalyst 의 lens 이전.

V3 Step 5-C (v3.0.0). 기존 ``src/agents/player_analyst.py:PlayerAnalyst`` 와 *내용 등가*.
페르소나 파일은 deprecated 마킹 유지 (Anti-pattern #1 — 즉시 삭제 금지). 호출 경로는
``src/agents/__init__.py`` 의 legacy alias 로 보존.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class StakeholderLens(LensRunner):
    lens_id: str = "stakeholder"
    name: str = "Stakeholder Lens (페르소나 PlayerAnalyst 이전)"
    suitable_intents: list = ["who_benefits", "what_happened"]
    suitable_event_types: list[str] = [
        "war", "diplomacy", "politics", "industry", "international_relations",
        "leadership_change", "election",
    ]
    method_steps: list[str] = [
        "핵심 행위자 식별 (국가/기업/인물/기관)",
        "각 행위자의 자원·레버리지·시간 압박 정리",
        "행위자 간 동맹·대립·경쟁·협력 관계 매핑",
        "권력 비대칭 + 의도-능력 분리",
    ]
    failure_modes: list[str] = [
        "비공식 행위자(시민·여론·미디어) 누락하기 쉬움",
        "정성적 평가에 의존 — 정량 검증 어려움",
        "단기 행위와 장기 구조의 분리 약함",
    ]
    system_prompt: str = (
        "당신은 이해관계자 분석가. 사건의 핵심 행위자 (국가/기업/인물/기관) 를 식별하고 "
        "각자의 자원·전략·위험도·관계를 분석한다. 권력 비대칭이 있다면 명시. "
        "비공식 행위자 (여론·미디어·시민 집단) 도 빠뜨리지 말 것. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
