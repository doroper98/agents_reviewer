"""decision_brief archetype — what_to_do 의도 전용. PLAN Appendix B.

V3 Step 5-C (v3.0.0). 사용 상황: 사용자가 *결정* 또는 *대응* 을 묻는 경우. event_type 무관 — 의도 전용.
섹션: 판단 요약 → 옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class DecisionBriefArchetype:
    archetype_id: str = "decision_brief"
    name: str = "Decision Brief"
    suitable_intents: list = ["what_to_do"]
    suitable_event_types: list[str] = []  # 의도 전용 — event_type 무관

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="db_1_judgment",
                title="판단 요약",
                purpose="현 시점의 핵심 판단과 권고의 결론 1문장",
                block_types=["narrative", "callout"],
            ),
            ReportSectionPlan(
                section_id="db_2_options",
                title="옵션 비교",
                purpose="가능한 옵션들과 비교 매트릭스",
                block_types=["decision_matrix", "matrix"],
            ),
            ReportSectionPlan(
                section_id="db_3_risks",
                title="옵션별 리스크",
                purpose="각 옵션의 부작용·실패 모드",
                block_types=["risk_matrix", "decomposition"],
            ),
            ReportSectionPlan(
                section_id="db_4_recommendation",
                title="권고",
                purpose="최종 권고 + 전제 조건",
                block_types=["narrative", "callout"],
            ),
            ReportSectionPlan(
                section_id="db_5_premortem",
                title="Pre-mortem",
                purpose="권고가 실패했다면 무엇이 사실이어야 하는가",
                block_types=["counter_hypothesis", "narrative"],
            ),
            ReportSectionPlan(
                section_id="db_6_signals",
                title="감시 신호",
                purpose="권고 무효화 조건 + 모니터링 지표",
                block_types=["watchlist"],
            ),
        ]

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = DecisionBriefArchetype()
