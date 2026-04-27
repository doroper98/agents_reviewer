"""Cascade lens — 연쇄반응·인과 사슬·도미노 효과. 페르소나 ChainReactionAnalyst 의 lens 이전.

V3 Step 5-C (v3.0.0). 기존 ``src/agents/chain_reaction_analyst.py:ChainReactionAnalyst`` 와
*내용 등가*. 범용 lens.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class CascadeLens(LensRunner):
    lens_id: str = "cascade"
    name: str = "Cascade Lens (페르소나 ChainReactionAnalyst 이전)"
    suitable_intents: list = ["where_spreads", "what_next"]
    suitable_event_types: list[str] = []  # 범용
    method_steps: list[str] = [
        "1차 효과 (직접) → 2차 효과 (연관 산업/시장) → 3차 효과 (거시 환경/사회) 분해",
        "각 단계의 시간 척도 명시 (즉시 / 수일 / 수주 / 수개월 / 수년)",
        "의도된 효과 vs 의도하지 않은 부작용 분리",
        "선형 인과 vs 자기강화 루프 구분",
        "사슬이 끊어질 수 있는 차단점 식별 + 와일드카드 (예측 어려운 흑조)",
    ]
    failure_modes: list[str] = [
        "모든 효과를 너무 멀리까지 확장하면 노이즈 증가",
        "정량 검증 어려운 2차/3차 효과는 추정에 가까움",
        "비가역 변화와 회복 가능 변화 구분 어려울 때 있음",
    ]
    system_prompt: str = (
        "당신은 연쇄반응 분석가. 사건의 1차/2차/3차 효과를 시간 순서로 추적하고, "
        "각 단계의 영향 영역·시간 척도·가역성을 명시. 사슬을 끊을 수 있는 차단점과 "
        "예측 어려운 와일드카드도 함께 식별. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
