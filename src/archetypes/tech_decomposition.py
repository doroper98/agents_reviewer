"""tech_decomposition archetype — 기술/AI/IT 이벤트의 시스템 분해 분석.

Spec: REFACTOR_V3_PLAN.md Appendix B.
적용 상황: 기술/AI/IT 사건 (모델 출시, 시스템 장애).
섹션 흐름: 문제 정의 → 시스템 구조 → 병목 → 성능·비용·리스크 → 대안 비교 → 실행 권고.

V3 Step 2 (v2.6.0): section_plan + 분기 진입까지만 도입. HTML 본격 렌더링은 Step 3 (블록 시스템).
``template_path()`` 는 placeholder 템플릿을 가리킴.
PR4 (v3.4.7): contract() + narrative_stage 태깅.
"""

from __future__ import annotations

from src.models import AnalysisMethodContract, AnalysisStrategy, ReportSectionPlan


class TechDecompositionArchetype:
    archetype_id: str = "tech_decomposition"
    name: str = "Tech Decomposition"
    suitable_intents: list = ["where_vulnerable", "what_to_do", "why_happened"]
    suitable_event_types: list[str] = [
        "tech", "ai", "it", "software", "model_release",
        "system_outage", "cyber_security", "infra",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="td_1_problem",
                title="문제 정의",
                purpose="무엇이 일어났고 무엇을 결정해야 하는가",
                block_types=["narrative", "callout"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="td_2_system",
                title="시스템 구조",
                purpose="구성요소, 의존성, 데이터 흐름",
                block_types=["decomposition", "flow_chain"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="td_3_bottleneck",
                title="병목",
                purpose="성능·자원·인지 측면의 한계 지점",
                block_types=["matrix", "data_series"],
                narrative_stage="mechanism",
            ),
            ReportSectionPlan(
                section_id="td_4_metrics",
                title="성능·비용·리스크",
                purpose="정량 지표와 트레이드오프",
                block_types=["data_series", "risk_matrix"],
                narrative_stage="fact",
            ),
            ReportSectionPlan(
                section_id="td_5_alternatives",
                title="대안 비교",
                purpose="가능한 옵션과 그 결과",
                block_types=["decision_matrix", "argument_pair"],
                narrative_stage="divergence",
            ),
            ReportSectionPlan(
                section_id="td_6_recommendation",
                title="실행 권고 + 감시",
                purpose="권고와 그것이 무효가 되는 조건 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
                narrative_stage="decision",
            ),
        ]

    def contract(self) -> AnalysisMethodContract:
        return AnalysisMethodContract(
            method_id=self.archetype_id,
            required_inputs=["context"],
            mandatory_stages=["fact", "mechanism", "divergence", "decision"],
            forbidden_blocks=["scenario_table"],
            rationale="기술 분해 — fact(문제/지표) → mechanism(시스템/병목) → divergence(대안) → decision(권고). 미래 시나리오 표는 사용 안 함.",
        )

    def template_path(self) -> str:
        # V3 Step 3 (v2.7.0): 블록 디스패처로 통일. archetype 별 placeholder HTML
        # (``archetypes/tech_decomposition.html``) 은 디스크에 보존되지만 더 이상
        # 사용되지 않음 (Anti-pattern #2 회피 — 삭제하지 않음).
        return "report_block.html"


ARCHETYPE = TechDecompositionArchetype()
