"""industry_value_chain archetype — 기업·산업 분석. PLAN Appendix B.

V3 Step 5-C (v3.0.0). 사용 상황: M&A, 공급망, 경쟁 구도, 산업 구조 변화.
섹션: 산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트.
PR4 (v3.4.7): contract() + narrative_stage 태깅.
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class IndustryValueChainArchetype:
    archetype_id: str = "industry_value_chain"
    name: str = "Industry Value Chain"
    suitable_intents: list = ["who_benefits", "where_vulnerable"]
    suitable_event_types: list[str] = [
        "industry", "company", "m_and_a", "value_chain",
        "competition", "supply_chain",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="ivc_1_structure",
                title="산업 구조",
                purpose="섹터 분류, 시장 규모, 진입 장벽",
                block_types=["narrative", "matrix"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="ivc_2_chain",
                title="가치사슬",
                purpose="upstream → midstream → downstream 단계와 각 단계의 marg",
                block_types=["flow_chain", "decomposition"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="ivc_3_competition",
                title="경쟁 구도",
                purpose="핵심 행위자, 시장점유, 차별화 축",
                block_types=["actor_cards", "matrix"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="ivc_4_pressure",
                title="수익성 압력",
                purpose="단기·중기 수익성에 작용하는 압력 + 비대칭",
                block_types=["risk_matrix", "data_series"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="ivc_5_options",
                title="전략 옵션",
                purpose="포지셔닝·M&A·통합·exit 등 전략 옵션 비교",
                block_types=["decision_matrix", "argument_pair"],
                narrative_stage="divergence",
            ),
            ReportSectionPlan(
                section_id="ivc_6_decision",
                title="의사결정 포인트 + 감시",
                purpose="결정 시점 / 트리거 + 감시 신호 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
                narrative_stage="trigger",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["context"],
            mandatory_stages=["fact", "mechanism", "divergence", "trigger"],
            forbidden_blocks=[],
            rationale="산업 분석 — fact(구조/경쟁) → mechanism(가치사슬/압력) → divergence(전략 옵션) → trigger(감시). decision_matrix 는 옵션 비교 차원에서 허용.",
        )

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = IndustryValueChainArchetype()
