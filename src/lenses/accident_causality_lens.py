"""Accident Causality lens — Fault Tree / Bow-Tie / Swiss Cheese / STAMP.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class AccidentCausalityLens(LensRunner):
    lens_id: str = "accident_causality"
    name: str = "Accident Causality Lens"
    suitable_intents: list = ["why_happened", "where_vulnerable", "what_to_do"]
    suitable_event_types: list[str] = [
        "accident", "disaster", "industrial", "natural_disaster",
        "fire", "explosion", "infra_failure", "safety",
    ]
    method_steps: list[str] = [
        "Fault Tree: 직접 원인 → 기여 원인의 OR/AND 트리 분해",
        "Bow-Tie: 원인 측 (preventive controls) + 결과 측 (mitigative controls) 동시 식별",
        "Swiss Cheese: 다층 방어막의 *구멍* 이 동시 정렬된 지점 — 각 층의 fail mode",
        "STAMP: 통제 구조의 의무·정보 흐름·피드백 루프 누락 점검 (시스템 차원)",
    ]
    failure_modes: list[str] = [
        "단일 사건만 보고 시스템 패턴(반복 사고) 놓치기 쉬움",
        "조직 문화·인센티브 구조의 영향 정량화 어려움",
        "외부 환경 변화 (규제·기후) 와의 상호작용 무시",
    ]
    system_prompt: str = (
        "당신은 사고·재난 분석가. Fault Tree / Bow-Tie / Swiss Cheese / STAMP 를 차례로 "
        "적용해 직접 원인 / 기여 원인 / 시스템적 누락 / 통제 구조 결함을 분리해서 짚는다. "
        "방어막 다층 구조를 우선 보고, 각 층의 구멍이 어떻게 정렬되었는지 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
