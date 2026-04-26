"""six_act_theater archetype — preserves current 6-act report flow.

V3 Step 2 (v2.6.0): 강등됨. archetype 옵션 1종으로 보존 (Anti-pattern #2 — 즉시 제거 금지).
``template_path()`` 는 기존 ``report.html`` 을 그대로 가리켜 byte-equal 출력 보장.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class SixActTheaterArchetype:
    archetype_id: str = "six_act_theater"
    name: str = "6막 극장"
    # Default fallback archetype — applies to all intents but best for 인물극형 사건.
    suitable_intents: list = [
        "what_happened", "why_happened", "who_benefits",
        "where_spreads", "what_next", "where_vulnerable", "what_to_do",
    ]
    suitable_event_types: list[str] = [
        "war", "diplomacy", "political_conflict", "international_relations",
        "leadership_change", "election", "general",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        # Section IDs/titles mirror the existing report.html acts (ACT I~VI).
        # Step 3 will use these to drive block rendering. In Step 2 this is informational —
        # the actual rendering still flows through the legacy macros in report.html.
        return [
            ReportSectionPlan(
                section_id="act_1_situation",
                title="ACT I — 상황인식",
                purpose="사건의 팩트, 타임라인, 핵심 수치",
                block_types=["narrative", "timeline", "data_series"],
            ),
            ReportSectionPlan(
                section_id="act_2_players",
                title="ACT II — 이해관계자",
                purpose="행위자 식별, 입장, 전략, 위험도",
                block_types=["actor_cards"],
            ),
            ReportSectionPlan(
                section_id="act_3_dynamics",
                title="ACT III — 구조 및 상호작용",
                purpose="비대칭, 피드백 루프, 전환점",
                block_types=["narrative", "matrix", "callout"],
            ),
            ReportSectionPlan(
                section_id="act_4_chain",
                title="ACT IV — 연쇄반응",
                purpose="인과 사슬, 도미노 효과, 차단점",
                block_types=["flow_chain", "callout"],
            ),
            ReportSectionPlan(
                section_id="act_5_scenarios",
                title="ACT V — 향후 시나리오",
                purpose="시나리오, 확률, 행위자별 영향",
                block_types=["scenario_table", "callout"],
            ),
            ReportSectionPlan(
                section_id="act_6_signals",
                title="ACT VI — 감시 시그널",
                purpose="시나리오 분기를 판별하는 핵심 신호",
                block_types=["watchlist", "counter_hypothesis"],
            ),
        ]

    def template_path(self) -> str:
        # Relative to src/templates/ — keeps the v2 file unchanged for byte-equal output.
        return "report.html"


# Singleton instance registered by registry.py at import time.
ARCHETYPE = SixActTheaterArchetype()
