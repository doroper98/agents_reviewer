"""Policy Implementation lens — Stakeholder Incentive Map / Distributional Impact /
Implementation Gap.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class PolicyImplementationLens(LensRunner):
    lens_id: str = "policy_implementation"
    name: str = "Policy Implementation Lens"
    suitable_intents: list = ["who_benefits", "what_to_do", "where_vulnerable"]
    suitable_event_types: list[str] = [
        "policy", "regulation", "law", "social", "real_estate",
        "labor", "tax", "subsidy",
    ]
    method_steps: list[str] = [
        "Stakeholder Incentive Map: 정책의 승자/패자 + 각자의 인센티브 구조",
        "Distributional Impact: 단기 vs 장기, 계층별 효과의 비대칭",
        "Implementation Gap: 정책 의도 vs 집행 현실의 격차 + 현실 제약 (행정·재정·정치)",
        "수정안 가능성: 부작용을 줄이면서 의도를 보존할 수 있는 변형",
    ]
    failure_modes: list[str] = [
        "단기 정치 변동 (선거 사이클) 무시",
        "비공식 제도(관습·문화) 둔감",
        "국제 조약·외부 압력 모델링 어려움",
    ]
    system_prompt: str = (
        "당신은 정책 집행 분석가. Stakeholder Incentive Map / Distributional Impact / "
        "Implementation Gap 을 적용해 정책의 승자·패자·구조적 한계를 짚는다. "
        "단기 vs 장기, 계층별 비대칭을 분리해서 보고, 의도-집행 격차를 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
