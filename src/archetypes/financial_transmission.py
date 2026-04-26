"""financial_transmission archetype — 금융·거시 이벤트의 전이 경로 분석.

Spec: REFACTOR_V3_PLAN.md Appendix B.
적용 상황: 시장/거시 사건 (환율, 금리, 자산 가격).
섹션 흐름: 가격 반응 → 포지션·자금흐름 → 전이 경로 → 취약 고리 → 스트레스 시나리오 → 관찰 지표.

V3 Step 2 (v2.6.0): section_plan + 분기 진입까지만 도입. HTML 본격 렌더링은 Step 3 (블록 시스템).
``template_path()`` 는 placeholder 템플릿을 가리킴.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class FinancialTransmissionArchetype:
    archetype_id: str = "financial_transmission"
    name: str = "Financial Transmission"
    suitable_intents: list = ["where_spreads", "where_vulnerable", "what_next"]
    suitable_event_types: list[str] = [
        "financial", "market", "macro", "currency", "interest_rate",
        "asset_price", "monetary_policy", "credit",
    ]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        return [
            ReportSectionPlan(
                section_id="ft_1_price_reaction",
                title="가격 반응",
                purpose="자산 가격의 즉시 반응과 변동성 측정",
                block_types=["data_series", "narrative"],
            ),
            ReportSectionPlan(
                section_id="ft_2_positioning",
                title="포지션·자금흐름",
                purpose="누가 어떤 포지션을 쥐고 있는지, 자금이 어디로 흐르는지",
                block_types=["matrix", "data_series"],
            ),
            ReportSectionPlan(
                section_id="ft_3_transmission",
                title="전이 경로",
                purpose="1차/2차/3차 전이 채널과 시간 척도",
                block_types=["flow_chain", "callout"],
            ),
            ReportSectionPlan(
                section_id="ft_4_vulnerabilities",
                title="취약 고리",
                purpose="스트레스 누적이 가장 큰 지점과 그 이유",
                block_types=["risk_matrix", "decomposition"],
            ),
            ReportSectionPlan(
                section_id="ft_5_stress_scenarios",
                title="스트레스 시나리오",
                purpose="기준·악화·꼬리 시나리오의 가격·자금 흐름 결과",
                block_types=["scenario_table", "data_series"],
            ),
            ReportSectionPlan(
                section_id="ft_6_observables",
                title="관찰 지표",
                purpose="시나리오 분기를 가리는 선행/동행 지표 + 반대 가설",
                block_types=["watchlist", "counter_hypothesis"],
            ),
        ]

    def template_path(self) -> str:
        # V3 Step 3 (v2.7.0): 블록 디스패처로 통일. archetype 별 placeholder HTML
        # (``archetypes/financial_transmission.html``) 은 디스크에 보존되지만 더 이상
        # 사용되지 않음 (Anti-pattern #2 회피 — 삭제하지 않음).
        return "report_block.html"


ARCHETYPE = FinancialTransmissionArchetype()
