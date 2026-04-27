"""Tech Architecture lens — Architecture Decomposition / Dependency Graph / Bottleneck Analysis.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class TechArchitectureLens(LensRunner):
    lens_id: str = "tech_architecture"
    name: str = "Tech Architecture Lens"
    suitable_intents: list = ["where_vulnerable", "what_to_do", "why_happened"]
    suitable_event_types: list[str] = [
        "tech", "ai", "it", "software", "model_release",
        "system_outage", "cyber_security", "infra", "platform",
    ]
    method_steps: list[str] = [
        "Architecture Decomposition: 시스템을 구성요소(레이어/서비스)로 분해",
        "Dependency Graph: 구성요소 간 의존 + 데이터 흐름",
        "Bottleneck Analysis: 성능·자원·인지 측면의 병목 후보 + 우선순위",
        "트레이드오프 명시: 성능 vs 비용 vs 신뢰성 vs 안전성 중 어느 축이 압박되는가",
    ]
    failure_modes: list[str] = [
        "인간 요인(운영자 오류·소셜 엔지니어링)에 약함",
        "비기술 거버넌스(법·윤리)에 둔감",
        "장기 진화 패턴 (모델 발전 곡선) 모델링 어려움",
    ]
    system_prompt: str = (
        "당신은 기술 시스템 분석가. Architecture Decomposition / Dependency Graph / "
        "Bottleneck Analysis 를 적용해 사건의 시스템적 본질을 짚는다. 구성요소·의존·병목을 "
        "분리해서 보고, 트레이드오프 축을 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
