"""timeline_first archetype — what_happened 의도 전용. PLAN Appendix B.

V3 Step 5-C (v3.0.0). 사용 상황: "현 상황만 빠르게 정리" 류. 사실·시간 순서 위주.
섹션: 핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항.
PR4 (v3.4.7): contract() + narrative_stage 태깅.
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class TimelineFirstArchetype:
    archetype_id: str = "timeline_first"
    name: str = "Timeline First"
    suitable_intents: list = ["what_happened"]
    suitable_event_types: list[str] = []  # 의도 전용

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="tf_1_summary",
                title="핵심 요약",
                purpose="3~5줄 시간 압축 — 무슨 일, 언제, 누구",
                block_types=["narrative", "callout"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="tf_2_timeline",
                title="사실 타임라인",
                purpose="시간 순서대로 검증된 이벤트만",
                block_types=["timeline"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="tf_3_figures",
                title="핵심 수치",
                purpose="규모·빈도·영향을 정량화하는 핵심 숫자",
                block_types=["data_series", "matrix"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="tf_4_sources",
                title="출처 평가",
                purpose="각 사실의 출처 신뢰도 (primary / secondary / expert)",
                block_types=["evidence_table"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="tf_5_open",
                title="미확인 사항 + 반대 가설",
                purpose="아직 검증 안 된 사실과 의혹 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
                narrative_stage="divergence",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["context"],
            mandatory_stages=["fact", "divergence"],
            forbidden_blocks=["decision_matrix", "scenario_table"],
            rationale="what_happened — 사실 정리가 본분. fact(요약/타임라인/수치/출처) + divergence(미확인) 만. 의사결정/시나리오는 다른 archetype.",
        )

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = TimelineFirstArchetype()
