"""mechanism_decomp archetype — why_happened 의도 전용. PLAN Appendix B.

V3 Step 5-C (v3.0.0). 사용 상황: "왜 이렇게 됐나, 메커니즘이 뭔지" 류. 표층-구조-제1원리 분해.
섹션: 표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해 → 정리.
PR3 (v3.4.6): narrative_stage 태깅 + contract().
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class MechanismDecompArchetype:
    archetype_id: str = "mechanism_decomp"
    name: str = "Mechanism Decomposition"
    suitable_intents: list = ["why_happened"]
    suitable_event_types: list[str] = []  # 의도 전용

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="md_1_surface",
                title="표층 현상",
                purpose="겉으로 드러난 현상의 정확한 기술",
                block_types=["narrative", "data_series"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="md_2_proximate",
                title="직접 원인",
                purpose="가까운 원인 — 시간적·공간적으로 인접한 요인",
                block_types=["flow_chain", "decomposition"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="md_3_structural",
                title="구조적 원인",
                purpose="제도·인센티브·구조적 압력 — 왜 이런 직접 원인이 생겼나",
                block_types=["decomposition", "narrative"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="md_4_first_principle",
                title="제1원리",
                purpose="가장 깊은 인과 — 다른 모든 원인이 결국 이 원리로 귀착",
                block_types=["callout", "narrative"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="md_5_misconceptions",
                title="흔한 오해",
                purpose="사람들이 자주 헷갈리는 인과 연결 + 정정",
                block_types=["argument_pair", "qna"],
                narrative_stage="divergence",
            ),
            ReportSectionPlan(
                section_id="md_6_synthesis",
                title="정리 + 반대 가설",
                purpose="3분 안에 설명 가능한 요약 + 반대 가설",
                block_types=["narrative", "counter_hypothesis"],
                narrative_stage="divergence",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["chain_reaction"],
            mandatory_stages=["fact", "mechanism", "divergence"],
            forbidden_blocks=["scenario_table", "decision_matrix"],
            rationale="메커니즘 분해 — 표층/직접/구조/제1원리는 모두 mechanism. divergence(반대 가설)로 마감. 시나리오/의사결정 매트릭스 금지.",
        )

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = MechanismDecompArchetype()
