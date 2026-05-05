"""V5 Phase 8 + 8A — Strategic Mode regression test.

REFACTOR_V5_PLAN.md §17.7 + §18.5 인수 기준:
    1. 전략 질의 패턴 매칭 정확도 ≥ 90% (수동 라벨 30건 검증).
    2. 전략 모드 보고서의 옵션 enumeration 100% ≥ 3개.
    3. 결정 매트릭스가 100% 등장.
    4. 권고가 100% 명시.
    5. 사용자 명시 기준 누락 0건.
    6. v4.5.7 가 잘못 처리한 사례 5건이 V5 에서 전략 모드로 라우팅.
    + 명시 prefix 7종 동작.
    + ActionPlan 30/60/90 비어있지 않음.
    + 옵션 0개 시 hold (AP-V5-18 갱신).

본 모듈은 #1~#5 + prefix 7종 + AP-V5-18 갱신 정책을 결정적으로 검증.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.agents.strategic_router import (
    EXPLICIT_PREFIXES,
    STRATEGIC_PATTERNS,
    ModeRouting,
    StrategicEvaluation,
    detect_strategic_intent,
    evaluate_strategic_mode,
    parse_explicit_prefix,
    route_query,
    run_strategic_kill_rules,
)
from src.state.models import (
    ActionItem,
    ActionPlan,
    Constraints,
    Criterion,
    DecisionMatrix,
    FailureMode,
    Recommendation,
    StrategicOption,
    StrategicReport,
)


# ─── 명시 Prefix 7종 SSOT ─────────────────────────────────────────


def test_explicit_prefixes_count_is_8() -> None:
    """Plan §18.2 의 명시 prefix 7종 + /strategy alias = 8."""
    # 7종 한국어 + /strategy = 총 8 entry.
    assert len(EXPLICIT_PREFIXES) == 8
    # 7개 mode 종류.
    expected_modes = {
        "strategic", "analytical", "forecast", "comparative",
        "geo_priority", "fast", "deep",
    }
    assert set(EXPLICIT_PREFIXES.values()) == expected_modes


def test_parse_explicit_prefix_strategic() -> None:
    mode, matched, cleaned = parse_explicit_prefix("?전략 LLM 도입 어떻게")
    assert mode == "strategic"
    assert matched == "?전략"
    assert cleaned == "LLM 도입 어떻게"


def test_parse_explicit_prefix_slash_strategy() -> None:
    mode, matched, cleaned = parse_explicit_prefix("/strategy decide on X")
    assert mode == "strategic"
    assert matched == "/strategy"


def test_parse_explicit_prefix_analytical() -> None:
    mode, _, cleaned = parse_explicit_prefix("?분석 미중 반도체 갈등")
    assert mode == "analytical"
    assert cleaned == "미중 반도체 갈등"


def test_parse_explicit_prefix_geo() -> None:
    mode, _, _ = parse_explicit_prefix("?지도 호르무즈 봉쇄")
    assert mode == "geo_priority"


def test_parse_explicit_prefix_no_prefix() -> None:
    mode, matched, cleaned = parse_explicit_prefix("일반 질의")
    assert mode is None
    assert matched == ""
    assert cleaned == "일반 질의"


def test_parse_explicit_prefix_only_at_start() -> None:
    """본문 *안* 의 prefix 같은 텍스트는 무시 (시작에만)."""
    mode, _, _ = parse_explicit_prefix("이건 ?전략 이라고 적힌 본문")
    assert mode is None


# ─── STRATEGIC_PATTERNS 8종 SSOT ──────────────────────────────────


def test_strategic_patterns_count_is_8() -> None:
    assert len(STRATEGIC_PATTERNS) == 8


def test_detect_strategic_intent_어떤_전략() -> None:
    is_strat, matched = detect_strategic_intent("이 사건에 어떤 전략이 좋을까")
    assert is_strat
    assert any("어떤 전략" in p for p in matched)


def test_detect_strategic_intent_어떻게_해야() -> None:
    is_strat, _ = detect_strategic_intent("Mac Studio 도입 어떻게 해야 할까")
    assert is_strat


def test_detect_strategic_intent_vs_pattern() -> None:
    is_strat, matched = detect_strategic_intent("자체 구축 vs 클라우드")
    assert is_strat
    assert any("vs" in p for p in matched)


def test_detect_strategic_intent_no_match() -> None:
    is_strat, matched = detect_strategic_intent("이스라엘 이란 충돌 분석")
    assert not is_strat
    assert matched == []


def test_detect_strategic_intent_옵션_평가() -> None:
    is_strat, _ = detect_strategic_intent("세 옵션 평가 부탁")
    assert is_strat


# ─── route_query 통합 ────────────────────────────────────────────


def test_route_query_explicit_prefix_wins() -> None:
    """명시 prefix 가 패턴/intent 보다 우선."""
    routing = route_query("?전략 무엇을 하든 상관없음")
    assert routing.mode == "strategic"
    assert routing.detection_source == "explicit_prefix"
    assert routing.matched_prefix == "?전략"


def test_route_query_pattern_strategic() -> None:
    routing = route_query("Mac Studio 도입 어떻게 해야 할까")
    assert routing.mode == "strategic"
    assert routing.detection_source == "pattern"


def test_route_query_llm_intent_what_to_do() -> None:
    """패턴 매칭 실패해도 LLM intent='what_to_do' 면 strategic."""
    routing = route_query(
        "이 결정을 위한 가이드 부탁",   # 패턴 매칭 X
        llm_user_intent="what_to_do",
    )
    assert routing.mode == "strategic"
    assert routing.detection_source == "llm_intent"


def test_route_query_default_analytical() -> None:
    """AP-V5-23 — 모호 시 analytical 기본값."""
    routing = route_query("이스라엘 이란 충돌 분석")
    assert routing.mode == "analytical"
    assert routing.detection_source == "default"


def test_route_query_geo_prefix() -> None:
    routing = route_query("?지도 호르무즈")
    assert routing.mode == "analytical"
    assert routing.geo_priority is True


def test_route_query_fast_prefix() -> None:
    routing = route_query("?짧게 윤리 논의")
    assert routing.fast_or_deep == "fast"


def test_route_query_deep_prefix() -> None:
    routing = route_query("?심층 미중 반도체 갈등 5년 흐름")
    assert routing.fast_or_deep == "deep"


# ─── Plan §17.7 인수 기준 #1 — 정확도 ≥ 90% ──────────────────────


# Golden Prompt 20건 + 추가 라벨 (총 ≥ 30건) — 수동 라벨링.
_LABELED_QUERIES: list[tuple[str, str]] = [
    # (query, expected_mode)  — strategic / analytical
    # Strategic
    ("Mac Studio M3 Ultra 256GB 도입 시 비용·성능·확장성을 고려한 전략 어떻게 해야 할까", "strategic"),
    ("사내 LLM 인프라 자체 구축 vs 클라우드 API 어떤 전략을 취해야 하지", "strategic"),
    ("스타트업 시리즈 A 다음 라운드 시기 비용·실탄·밸류에이션 고려했을 때 어떻게 해야", "strategic"),
    ("?전략 무엇이든", "strategic"),
    ("/strategy decide", "strategic"),
    ("이번 결정 어떤 길로 가야 하나", "strategic"),
    ("세 옵션 평가 비교", "strategic"),
    ("어디로 가야 할지", "strategic"),
    ("어떤 결정 취해야 할까", "strategic"),
    ("ABC 비교 vs 결정", "strategic"),
    # Analytical
    ("이스라엘-이란 충돌 가능성을 다음 6개월 시각으로 분석", "analytical"),
    ("대만 해협 위기 시나리오를 면밀하게 분석", "analytical"),
    ("북한 7차 핵실험 가능성 한국-일본 안보 영향 심층 분석", "analytical"),
    ("엔 캐리 unwind 가 KOSPI 200 옵션 변동성에 미치는 전이 채널 분석", "analytical"),
    ("FOMC 50bp 인하 시 한국 채권 시장 전이 분석", "analytical"),
    ("비트코인 스팟 ETF 자금 유입과 매크로 유동성 상관 분석", "analytical"),
    ("Claude 4.7 출시가 LG에너지솔루션 c-DN 시뮬레이션 통합에 갖는 함의", "analytical"),
    ("TSMC 2nm 양산 일정 지연이 HBM4 공급망에 미치는 영향", "analytical"),
    ("OpenAI o3 추론 모델 공개가 Anthropic Sonnet 4.6 포지셔닝에 끼치는 영향", "analytical"),
    ("EU AI Act 의 high-risk 분류가 우리 회사 LLM 도입에 미치는 영향 분석", "analytical"),
    ("한국 가상자산 과세 유예 결정의 시장 영향 분석", "analytical"),
    ("호르무즈 해협 봉쇄 시 한국 LNG·원유 공급망 영향 분석", "analytical"),
    ("남중국해 베트남-필리핀 EEZ 분쟁 자원 영향", "analytical"),
    ("윤리학적 관점에서 LLM 의 의사결정 보조의 한계 논의", "analytical"),
    ("지난 5년 미중 반도체 갈등 전체 흐름과 향후 시나리오", "analytical"),
    ("글로벌 AI 거버넌스 10년 전망 — EU/US/중국/한국 정책", "analytical"),
    ("?분석 OpenAI 제품 전략", "analytical"),
    ("?예측 한국 반도체 수출 6개월", "analytical"),
    ("?비교 GPT-5 vs Claude 4.7 capability", "analytical"),
    ("?지도 인도-파키스탄 국경", "analytical"),
]


def test_routing_accuracy_at_least_90_percent() -> None:
    """Plan §17.7 #1 — 패턴 매칭 정확도 ≥ 90% (수동 라벨 30건)."""
    correct = 0
    misclassified: list[tuple[str, str, str]] = []
    for query, expected in _LABELED_QUERIES:
        routing = route_query(query)
        if routing.mode == expected:
            correct += 1
        else:
            misclassified.append((query, expected, routing.mode))

    rate = correct / len(_LABELED_QUERIES)
    assert rate >= 0.90, (
        f"정확도 미달 — {correct}/{len(_LABELED_QUERIES)} = {rate:.0%} < 90%. "
        f"Misclassified: {misclassified}"
    )


# ─── StrategicReport 모델 ────────────────────────────────────────


def test_strategic_report_8_required_outputs() -> None:
    """Plan §18.3 의 8개 필수 출력 필드."""
    expected_fields = {
        "decision_statement", "options", "criteria", "constraints",
        "decision_matrix", "recommendation", "kill_switch_conditions",
        "action_plan_30_60_90",
    }
    actual = set(StrategicReport.model_fields.keys())
    assert expected_fields <= actual


def test_constraints_3_risk_tolerance_levels() -> None:
    from typing import get_args
    levels = set(get_args(Constraints.model_fields["risk_tolerance"].annotation))
    assert levels == {"low", "medium", "high"}


def test_constraints_3_reversibility() -> None:
    from typing import get_args
    rev = set(get_args(Constraints.model_fields["reversibility"].annotation))
    assert rev == {"reversible", "partial", "irreversible"}


def test_failure_mode_severity_3_enum() -> None:
    from typing import get_args
    sev = set(get_args(FailureMode.model_fields["severity"].annotation))
    assert sev == {"low", "medium", "high"}


# ─── KILL_RULES_STRATEGIC ────────────────────────────────────────


def _clean_strategic_report(mode: str = "standard") -> StrategicReport:
    """모든 KILL_RULES 통과하는 정상 전략 보고서."""
    return StrategicReport(
        decision_statement="Mac Studio 도입 여부.",
        options=[
            StrategicOption(
                label="옵션 A",
                one_line_summary="Mac Studio 도입",
                core_actions=["주문", "설치"],
                pre_mortem=[FailureMode(mode="가격 급등", leading_indicator="환율")],
            ),
            StrategicOption(
                label="옵션 B",
                one_line_summary="클라우드 GPU",
                core_actions=["계정", "인스턴스"],
                pre_mortem=[FailureMode(mode="rate limit", leading_indicator="대기열")],
            ),
            StrategicOption(
                label="옵션 C",
                one_line_summary="현재 유지",
                core_actions=["유지"],
                pre_mortem=[FailureMode(mode="기회 손실", leading_indicator="경쟁사 출시")],
            ),
        ],
        criteria=[
            Criterion(name="비용", weight=1.0),
            Criterion(name="성능", weight=1.0),
            Criterion(name="확장성", weight=1.0),
        ],
        decision_matrix=DecisionMatrix(
            options=["옵션 A", "옵션 B", "옵션 C"],
            criteria=["비용", "성능", "확장성"],
            scores=[[3, 4, 3], [5, 5, 4], [5, 2, 1]],
        ),
        recommendation=Recommendation(
            selected_option_label="옵션 A",
            rationale=(
                "옵션 A 가 성능 + 확장성 종합 우위. 한 번 결제로 3년 이상 활용 가능 "
                "라 비용 효율도 1년 만에 break-even. 클라우드 의존성 없음."
            ),
            rationale_points=["성능 우위", "확장성", "비용 효율"],
        ),
        kill_switch_conditions=["환율 급등 시 옵션 B 로 전환", "vendor 출시 지연"],
        action_plan_30_60_90=ActionPlan(
            days_30=[ActionItem(action="구매 결재")],
            days_60=[ActionItem(action="설치 완료")],
            days_90=[ActionItem(action="성능 측정 + ROI 확인")],
        ),
        user_provided_criteria=["비용", "성능", "확장성"],
        mode=mode,
    )


def test_kill_clean_report_passes() -> None:
    report = _clean_strategic_report("deep")
    triggered = run_strategic_kill_rules(report, mode="deep")
    assert triggered == []


def test_kill_decision_statement_missing() -> None:
    report = _clean_strategic_report()
    report.decision_statement = ""
    triggered = run_strategic_kill_rules(report)
    assert "decision_statement_missing" in triggered


def test_kill_no_decision_matrix() -> None:
    report = _clean_strategic_report()
    report.decision_matrix = DecisionMatrix()  # 빈 matrix
    triggered = run_strategic_kill_rules(report)
    assert "no_decision_matrix" in triggered


def test_kill_recommendation_absent() -> None:
    report = _clean_strategic_report()
    report.recommendation = None
    triggered = run_strategic_kill_rules(report)
    assert "recommendation_absent" in triggered


def test_kill_recommendation_short_rationale() -> None:
    report = _clean_strategic_report()
    report.recommendation = Recommendation(
        selected_option_label="옵션 A",
        rationale="짧음",  # < 50자
    )
    triggered = run_strategic_kill_rules(report)
    assert "recommendation_absent" in triggered


def test_kill_premortem_missing_deep_mode() -> None:
    """deep 모드에서 어떤 옵션도 pre_mortem 없으면 KILL."""
    report = _clean_strategic_report("deep")
    for opt in report.options:
        opt.pre_mortem = []
    triggered = run_strategic_kill_rules(report, mode="deep")
    assert "premortem_missing_deep" in triggered


def test_kill_premortem_missing_standard_mode_ok() -> None:
    """standard 모드에선 pre_mortem 없어도 OK."""
    report = _clean_strategic_report("standard")
    for opt in report.options:
        opt.pre_mortem = []
    triggered = run_strategic_kill_rules(report, mode="standard")
    assert "premortem_missing_deep" not in triggered


def test_kill_criteria_not_user_aligned() -> None:
    """사용자 명시 기준 (A/B/C) 가 매트릭스에 누락되면 KILL."""
    report = _clean_strategic_report()
    report.user_provided_criteria = ["비용", "시간"]   # "시간" 추가 — 매트릭스에 없음
    triggered = run_strategic_kill_rules(report)
    assert "criteria_not_user_aligned" in triggered


def test_kill_action_plan_missing() -> None:
    report = _clean_strategic_report()
    report.action_plan_30_60_90 = ActionPlan()   # 모두 빈
    triggered = run_strategic_kill_rules(report)
    assert "action_plan_missing" in triggered


def test_kill_kill_switch_missing() -> None:
    report = _clean_strategic_report()
    report.kill_switch_conditions = []
    triggered = run_strategic_kill_rules(report)
    assert "kill_switch_missing" in triggered


def test_kill_matrix_score_uniform() -> None:
    """모든 셀이 동일 점수 → 분석 무의미."""
    report = _clean_strategic_report()
    report.decision_matrix.scores = [[3, 3, 3], [3, 3, 3], [3, 3, 3]]
    triggered = run_strategic_kill_rules(report)
    assert "matrix_score_uniform" in triggered


# ─── AP-V5-18 갱신 — 옵션 0개 hold, 1~5 허용, 6+ KILL ────────────


def test_ap_v5_18_options_zero_hold() -> None:
    """옵션 0개 → hold + 사용자 안내 (KILL 아님)."""
    report = _clean_strategic_report()
    report.options = []
    triggered = run_strategic_kill_rules(report)
    assert "options_zero_hold" in triggered


def test_ap_v5_18_options_one_allowed() -> None:
    """옵션 1개 — 단일 옵션 권고. KILL 아님."""
    report = _clean_strategic_report()
    report.options = [report.options[0]]
    triggered = run_strategic_kill_rules(report)
    assert "options_too_few" not in triggered
    assert "options_too_many" not in triggered


def test_ap_v5_18_options_two_allowed() -> None:
    """옵션 2개 — Plan §18.4 갱신 후 허용."""
    report = _clean_strategic_report()
    report.options = report.options[:2]
    triggered = run_strategic_kill_rules(report)
    assert "options_too_few" not in triggered


def test_ap_v5_18_options_six_kill() -> None:
    """옵션 6개 이상 → 분석 마비, KILL."""
    report = _clean_strategic_report()
    report.options = [
        StrategicOption(label=f"옵션 {i}", one_line_summary=f"x{i}")
        for i in range(6)
    ]
    triggered = run_strategic_kill_rules(report)
    assert "options_too_many" in triggered


# ─── evaluate_strategic_mode 통합 ────────────────────────────────


def test_evaluate_clean_publishes() -> None:
    report = _clean_strategic_report("deep")
    result = evaluate_strategic_mode(report, mode="deep")
    assert result.decision == "publish"
    assert result.triggered_rules == []


def test_evaluate_zero_options_holds() -> None:
    """옵션 0개 → hold + 안내."""
    report = _clean_strategic_report()
    report.options = []
    result = evaluate_strategic_mode(report)
    assert result.decision == "hold"
    assert "전략 질의 성립 불가" in result.hold_reason
    assert "?분석" in result.hold_reason


def test_evaluate_decision_kill() -> None:
    report = _clean_strategic_report()
    report.decision_statement = ""    # KILL trigger
    result = evaluate_strategic_mode(report)
    assert result.decision == "kill"
    assert "decision_statement_missing" in result.triggered_rules


def test_evaluate_options_too_many_kills() -> None:
    report = _clean_strategic_report()
    report.options = [
        StrategicOption(label=f"옵션 {i}", one_line_summary=f"x{i}")
        for i in range(7)
    ]
    result = evaluate_strategic_mode(report)
    assert result.decision == "kill"
    assert "options_too_many" in result.triggered_rules
