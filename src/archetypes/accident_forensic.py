"""accident_forensic archetype — 사고·재난 (산업재해, 자연재해).

Spec: REFACTOR_V3_PLAN.md Appendix B.
적용 상황: 사고·재난 (산업재해, 자연재해).
섹션 흐름: 사실 타임라인 → 직접 원인 → 방어막 실패 → 조직적 원인 → 재발 방지 → 미해결 질문.

V3 Step 5-A (v2.9.0) 도입.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class AccidentForensicArchetype:
    archetype_id: str = "accident_forensic"
    name: str = "Accident Forensic"
    suitable_intents: list = ["why_happened", "where_vulnerable", "what_to_do"]
    suitable_event_types: list[str] = [
        "accident", "disaster", "industrial", "natural_disaster",
        "fire", "explosion", "infra_failure", "safety",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="af_1_timeline",
                title="사실 타임라인",
                purpose="사고 전·발생·이후의 시간 순서 사실",
                block_types=["timeline", "narrative"],
            ),
            ReportSectionPlan(
                section_id="af_2_proximate",
                title="직접 원인",
                purpose="사고를 직접 촉발한 요소 (Fault Tree 의 leaf)",
                block_types=["flow_chain", "callout"],
            ),
            ReportSectionPlan(
                section_id="af_3_swiss_cheese",
                title="방어막 실패",
                purpose="다층 방어막의 구멍이 정렬된 지점 (Swiss Cheese)",
                block_types=["decomposition", "matrix"],
            ),
            ReportSectionPlan(
                section_id="af_4_organizational",
                title="조직적 원인",
                purpose="STAMP — 통제 구조·정보 흐름·피드백 루프 누락",
                block_types=["narrative", "decomposition"],
            ),
            ReportSectionPlan(
                section_id="af_5_prevention",
                title="재발 방지",
                purpose="구체적 방지책 + 우선순위 + 비용/현실성 검토",
                block_types=["risk_matrix", "decision_matrix"],
            ),
            ReportSectionPlan(
                section_id="af_6_open",
                title="미해결 질문 + 반대 가설",
                purpose="조사가 답하지 못한 부분 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
            ),
        ]

    def template_path(self) -> str:
        return "report_block.html"


ARCHETYPE = AccidentForensicArchetype()
