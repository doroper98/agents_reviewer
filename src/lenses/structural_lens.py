"""Structural lens — 구조적 원인·힘의 역학·피드백 루프. 페르소나 DynamicsAnalyst 의 lens 이전.

V3 Step 5-C (v3.0.0). 기존 ``src/agents/dynamics_analyst.py:DynamicsAnalyst`` 와 *내용 등가*.
범용 lens — suitable_event_types 비워둠 (모든 사건에 적용 가능).
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class StructuralLens(LensRunner):
    lens_id: str = "structural"
    name: str = "Structural Lens (페르소나 DynamicsAnalyst 이전)"
    suitable_intents: list = ["why_happened", "where_vulnerable"]
    suitable_event_types: list[str] = []  # 범용
    method_steps: list[str] = [
        "분석 시각 선택 (게임이론/시스템 사고/경로 의존성/네트워크/행동경제학 중 2~3 조합)",
        "핵심 갈등·긴장 구조 명시 (core_tension)",
        "비대칭 (자원/정보/시간/정당성) 식별",
        "피드백 루프 (강화·균형) 와 전환점 도출",
        "왜 쉽게 해소되지 않는가 — 구조적 이유",
    ]
    failure_modes: list[str] = [
        "단일 프레임워크 강제 시 사건의 본질 왜곡",
        "정량 데이터 부족하면 추상화에 빠지기 쉬움",
        "단기 행위 변동을 구조 변화로 오해",
    ]
    system_prompt: str = (
        "당신은 구조 분석가. 사건의 이면의 구조적 원인과 힘의 역학을 분석한다. "
        "게임이론·시스템 사고·경로 의존성·네트워크·행동경제학 등을 사건 성격에 맞게 "
        "2~3개 조합. 비대칭과 피드백 루프, 전환점을 명시. 반대 가설을 함께 보존. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
