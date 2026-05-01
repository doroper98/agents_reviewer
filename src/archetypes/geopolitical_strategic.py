"""geopolitical_strategic archetype — 지정학·전쟁 (군사 행동, 안보 위기).

Spec: REFACTOR_V3_PLAN.md Appendix B.
적용 상황: 지정학·전쟁 (군사 행동, 안보 위기).
섹션 흐름: 사건 요약 → 전장·행위자 → 의도와 능력 → 확전 경로 → 억제 요인 → 감시 신호.

V3 Step 5-A (v2.9.0) 도입. ``template_path()`` 는 블록 디스패처를 가리킴.
PR4 (v3.4.7): contract() + narrative_stage 태깅.
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class GeopoliticalStrategicArchetype:
    archetype_id: str = "geopolitical_strategic"
    name: str = "Geopolitical Strategic"
    suitable_intents: list = ["who_benefits", "what_next", "where_vulnerable"]
    suitable_event_types: list[str] = [
        "war", "diplomacy", "security", "international_relations",
        "geopolitical", "military_action", "alliance",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="gs_1_summary",
                title="사건 요약",
                purpose="현재 상황의 핵심 팩트와 시점",
                block_types=["narrative", "timeline"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="gs_2_battlefield",
                title="전장·행위자",
                purpose="공간적 무대와 핵심 행위자 배치",
                # v3.4.0: 전장 섹션에 maplibre+d3-geo 지도 블록 추가.
                # 데이터 없으면 _payload_map → None → 자동 스킵.
                block_types=["map", "actor_cards", "callout"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="gs_3_intent_capability",
                title="의도와 능력",
                purpose="각 행위자의 능력 vs 의도 분리 — Capability-Intent Matrix",
                block_types=["matrix", "narrative"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="gs_4_escalation",
                title="확전 경로",
                purpose="Escalation Ladder 위치 + 다음 가능 경로 1~2 단계",
                block_types=["flow_chain", "scenario_table"],
                narrative_stage="divergence",
            ),
            ReportSectionPlan(
                section_id="gs_5_deterrent",
                title="억제 요인",
                purpose="확전을 막는 구조적·외교적 제약 + 그 한계",
                block_types=["decomposition", "callout"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="gs_6_signals",
                title="감시 신호 + 반대 가설",
                purpose="시나리오 분기를 가리는 선행 지표 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
                narrative_stage="trigger",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["context", "players"],
            mandatory_stages=["fact", "mechanism", "divergence", "trigger"],
            forbidden_blocks=["decision_matrix"],
            rationale="지정학 — fact(사건/전장) → mechanism(의도/억제) → divergence(확전 경로) → trigger(감시). 의사결정 매트릭스는 별도 archetype.",
        )

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = GeopoliticalStrategicArchetype()
