"""scenario_first archetype — what_next 의도 전용. PLAN Appendix B.

V3 Step 5-C (v3.0.0). 사용 상황: "앞으로 어떻게 될 것인가" 류. 시나리오 분기 위주.
섹션: 기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호.
PR3 (v3.4.6): narrative_stage 태깅 + contract() 선언.
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class ScenarioFirstArchetype:
    archetype_id: str = "scenario_first"
    name: str = "Scenario First"
    suitable_intents: list = ["what_next"]
    suitable_event_types: list[str] = []  # 의도 전용

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="sf_1_base",
                title="기준 시나리오",
                purpose="가장 가능성 높은 전개 (50~60% 확률)",
                block_types=["narrative", "scenario_table"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="sf_2_branches",
                title="분기 시나리오",
                purpose="기준에서 갈라지는 2~4개 분기 + 각 확률·트리거",
                block_types=["scenario_table", "flow_chain"],
                narrative_stage="divergence",
            ),
            ReportSectionPlan(
                section_id="sf_3_bayesian",
                title="베이지안 업데이트 가이드",
                purpose="새 정보가 들어왔을 때 확률을 어떻게 갱신할지",
                block_types=["matrix", "narrative"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="sf_4_signals",
                title="감시 신호 + 반대 가설",
                purpose="시나리오 분기를 가리는 선행 지표 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
                narrative_stage="trigger",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["scenarios"],
            mandatory_stages=["fact", "divergence", "trigger"],
            forbidden_blocks=["decision_matrix"],  # 의사결정은 decision_brief 영역
            rationale="시나리오 분기 위주 — fact(기준) → divergence(분기) → trigger(감시)가 핵심. 의사결정 매트릭스 금지.",
        )

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = ScenarioFirstArchetype()
