"""policy_implementation archetype — 정책·사회 (법안, 규제, 사회 변화).

Spec: REFACTOR_V3_PLAN.md Appendix B.
적용 상황: 정책·사회 (법안, 규제, 사회 변화).
섹션 흐름: 정책 의도 → 이해관계자 → 제약 조건 → 집행 가능성 → 부작용 → 수정안.

V3 Step 5-A (v2.9.0) 도입.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class PolicyImplementationArchetype:
    archetype_id: str = "policy_implementation"
    name: str = "Policy Implementation"
    suitable_intents: list = ["who_benefits", "what_to_do", "where_vulnerable"]
    suitable_event_types: list[str] = [
        "policy", "regulation", "law", "social", "real_estate",
        "labor", "tax", "subsidy",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="pi_1_intent",
                title="정책 의도",
                purpose="정책 설계자가 의도한 결과 + 명목적 목적",
                block_types=["narrative", "callout"],
            ),
            ReportSectionPlan(
                section_id="pi_2_stakeholders",
                title="이해관계자",
                purpose="승자/패자 + 인센티브 구조 (Stakeholder Incentive Map)",
                block_types=["actor_cards", "matrix"],
            ),
            ReportSectionPlan(
                section_id="pi_3_constraints",
                title="제약 조건",
                purpose="행정·재정·정치·법적 제약 + 외부 압력",
                block_types=["decomposition", "narrative"],
            ),
            ReportSectionPlan(
                section_id="pi_4_feasibility",
                title="집행 가능성",
                purpose="Implementation Gap — 의도 vs 집행 현실의 격차",
                block_types=["scenario_table", "callout"],
            ),
            ReportSectionPlan(
                section_id="pi_5_side_effects",
                title="부작용",
                purpose="Distributional Impact — 단기/장기 비대칭 + 비의도 결과",
                block_types=["risk_matrix", "decomposition"],
            ),
            ReportSectionPlan(
                section_id="pi_6_revisions",
                title="수정안 + 감시 신호",
                purpose="부작용을 줄이며 의도를 보존하는 변형 + 효과 모니터링 신호 + 반대 가설",
                block_types=["decision_matrix", "watchlist", "counter_hypothesis"],
            ),
        ]

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = PolicyImplementationArchetype()
