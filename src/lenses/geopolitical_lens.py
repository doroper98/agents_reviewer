"""Geopolitical lens — DIME / PMESII / Escalation Ladder / Capability-Intent Matrix.

Spec: REFACTOR_V3_PLAN.md Appendix C.
"""

from __future__ import annotations

from src.lenses.base import LensRunner


class GeopoliticalLens(LensRunner):
    lens_id: str = "geopolitical"
    name: str = "Geopolitical Lens"
    suitable_intents: list = ["who_benefits", "what_next", "where_vulnerable"]
    suitable_event_types: list[str] = [
        "war", "diplomacy", "international_relations", "security",
        "geopolitical", "political_conflict", "leadership_change",
    ]
    method_steps: list[str] = [
        "DIME 4축 분해: 외교(D)/정보(I)/군사(M)/경제(E) 도구 중 어느 것이 핵심인지 식별",
        "PMESII 6차원 환경 점검: 정치/군사/경제/사회/정보/인프라",
        "Escalation Ladder 위치 추정 — 현 단계의 다음 가능 단계 1~2개",
        "Capability-Intent Matrix 로 행위자별 능력 vs 의도 분리",
    ]
    failure_modes: list[str] = [
        "비국가 행위자(테러·해커·시민 봉기)에 약함",
        "경제 데이터 디테일 부족",
        "내부 정치 균형(파벌)에 둔감",
    ]
    system_prompt: str = (
        "당신은 지정학 분석가. DIME/PMESII/Escalation Ladder/Capability-Intent Matrix 를 "
        "조합해 사건의 지정학적 동학을 분석한다. 각 행위자의 *능력* 과 *의도* 를 분리해서 보고, "
        "현재 escalation 단계의 다음 가능 경로 1~2 개를 명시한다. 음슴체."
    )

    def _abstract_marker(self) -> None:
        pass
