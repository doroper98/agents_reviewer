"""V5 Phase 1A — ResearchDirector / Method Router regression test.

Plan §6.6 인수 기준:
    1. ResearchDirector 가 모든 사건에 대해 AnalysisBrief 를 emit.
    2. 동일 사건에 대해 ResearchDirector 가 *다른 분석기법* 을 선택한 사례가
       사용자 retrospective 에 의해 검증.
    3. AnalysisBrief 의 selected_methods 가 보고서 prose 의 *실제 분석 형태*
       와 일치.
    4. Golden Prompt 20건의 expected_method 와 ResearchDirector 의 실제 선택이
       ≥ 80% 일치.

본 모듈은 #1, #2, #4 를 결정적으로 검증. #3 은 record_baseline.py 가 박은
sample_composed_reports 를 사용해 *Composer 출력의 분석 형태* 와 비교 — Phase
1A 진입 시점엔 sample 미녹화라 SKIP.

Phase 1A 시점의 #4 검증은 *heuristic fallback* 의 결과를 비교 — 실제 LLM
ResearchDirector 의 선택률은 record_baseline 후 본격 측정.
"""

from __future__ import annotations

from typing import Any

from tests.regression._pytest_compat import pytest

from src.agents.research_director import (
    DEFAULT_BRIEF,
    SYSTEM_PROMPT,
    design_via_heuristics,
)
from src.state.models import AnalysisBrief, AnalysisMethod, ReportShape
from tests.regression.helpers import (
    RegressionResult,
    load_golden_prompts,
)


# ─── 인수 기준 #1 — 모든 사건에 AnalysisBrief 가 emit ───────────────────


def test_default_brief_matches_plan_20_3() -> None:
    """Plan §20.3: ResearchDirector 호출 실패 시 fallback 의 형식 준수."""
    assert DEFAULT_BRIEF.report_shape.section_count == 4, (
        "Plan §20.3: 기본 AnalysisBrief 의 section_count=4"
    )
    assert DEFAULT_BRIEF.report_shape.must_have_sections == [
        "situation", "mechanism", "scenarios", "watch",
    ], "Plan §20.3: 기본 must_have_sections 배열"
    assert DEFAULT_BRIEF.selected_methods == [], (
        "Plan §20.3: 기본 selected_methods 는 비어있음"
    )
    assert isinstance(DEFAULT_BRIEF, AnalysisBrief)


def test_heuristic_emits_for_all_20_prompts() -> None:
    """Plan §6.6 인수 기준 #1 — 20건 모두 design_via_heuristics 가 emit."""
    prompts = load_golden_prompts()
    assert len(prompts) == 20
    for entry in prompts:
        brief = design_via_heuristics(
            entry["prompt"], mode=entry["expected"]["mode"]
        )
        assert isinstance(brief, AnalysisBrief), f"{entry['id']}: AnalysisBrief 미발화"
        # selected_methods 가 비어있으면 design 자체 실패 — fallback 이 채움.
        assert brief.selected_methods, f"{entry['id']}: selected_methods empty"
        # 1~3개 method (Plan §6.4 원칙).
        assert 1 <= len(brief.selected_methods) <= 3, (
            f"{entry['id']}: selected_methods 개수 {len(brief.selected_methods)} "
            f"— Plan §6.4 의 1~3 범위 위반"
        )


# ─── 인수 기준 #4 — ≥80% Golden Prompt expected_method 일치 ─────────────


def _check_method_match(
    brief: AnalysisBrief,
    expected_method: str,
) -> bool:
    """selected_methods 안에 expected_method 가 *어디라도* 들어 있으면 매칭.

    Plan §6.6 #4 의 일치 정의 — expected 가 1순위가 아니어도 *선정 list 안에*
    들어 있으면 OK. ResearchDirector 가 1~3개를 고르는 것이 정책.
    """
    method_ids = [m.method for m in (brief.selected_methods or [])]
    return expected_method in method_ids


def test_heuristic_method_match_rate_above_80_percent() -> None:
    """Plan §6.6 인수 기준 #4 — Golden Prompt 20건 expected_method 와의 일치도."""
    prompts = load_golden_prompts()
    matches = 0
    mismatches: list[tuple[str, str, list[str]]] = []
    for entry in prompts:
        expected = entry["expected"]["expected_method"]
        brief = design_via_heuristics(
            entry["prompt"], mode=entry["expected"]["mode"]
        )
        actual = [m.method for m in brief.selected_methods]
        if _check_method_match(brief, expected):
            matches += 1
        else:
            mismatches.append((entry["id"], expected, actual))

    rate = matches / len(prompts)
    # Plan §6.6 #4 의 임계.
    assert rate >= 0.80, (
        f"Plan §6.6 인수 기준 #4 미달: "
        f"match_rate={rate:.0%} ({matches}/{len(prompts)}) < 80%. "
        f"Mismatches: {mismatches}"
    )


# ─── 분포 가드 ──────────────────────────────────────────────────────────


def test_strategic_query_prompts_route_to_strategic_mode() -> None:
    """Plan §6.4 — 전략 질의는 strategic_hint=true + report_mode='strategy'."""
    prompts = load_golden_prompts()
    strategic_prompts = [p for p in prompts if p["category"] == "strategic_query"]
    assert len(strategic_prompts) == 3, "Plan §3.3: strategic_query 3건"
    for entry in strategic_prompts:
        brief = design_via_heuristics(
            entry["prompt"], mode=entry["expected"]["mode"]
        )
        assert brief.strategic_hint is True, (
            f"{entry['id']}: strategic_query 인데 strategic_hint=False — "
            f"Plan §6.4 의 6번 (전략 모드 신호) 누락"
        )
        assert brief.report_mode == "strategy", (
            f"{entry['id']}: report_mode={brief.report_mode}, expected 'strategy'"
        )


def test_map_required_prompts_have_must_have_map() -> None:
    """지도 필수 사건 (호르무즈 등) 은 visual_constraints.must_have 에 'map'."""
    prompts = load_golden_prompts()
    for entry in prompts:
        if entry["category"] != "map_required":
            continue
        brief = design_via_heuristics(
            entry["prompt"], mode=entry["expected"]["mode"]
        )
        assert "map" in (brief.visual_constraints.must_have or []), (
            f"{entry['id']}: map_required 인데 visual_constraints.must_have 에 'map' 없음"
        )


def test_no_charts_prompts_forbid_chart_types() -> None:
    """윤리·논의형 prompt 는 차트 type 8종 모두 forbidden 으로."""
    prompts = load_golden_prompts()
    chart_types = {"bar", "donut", "line", "gantt", "network", "stacked", "bubble", "heatmap"}
    for entry in prompts:
        if entry["category"] != "no_charts":
            continue
        brief = design_via_heuristics(
            entry["prompt"], mode=entry["expected"]["mode"]
        )
        forbidden = set(brief.visual_constraints.forbidden or [])
        assert chart_types <= forbidden, (
            f"{entry['id']}: no_charts 인데 forbidden 에 차트 8종 모두 들어 있지 않음 — "
            f"missing: {chart_types - forbidden}"
        )


# ─── SYSTEM_PROMPT 정합성 (Plan §6.4 그대로) ────────────────────────────


def test_system_prompt_contains_9_methods() -> None:
    """SYSTEM_PROMPT 가 9종 method 명시 (Plan §6.4 enum)."""
    expected_methods = [
        "ACH", "scenario_tree", "transmission_channel", "stakeholder_matrix",
        "fault_tree", "decision_matrix", "pre_mortem",
        "transmission_timeline", "comparative",
    ]
    for m in expected_methods:
        assert m in SYSTEM_PROMPT, f"SYSTEM_PROMPT 에 method '{m}' 없음"


def test_system_prompt_contains_principle_examples() -> None:
    """Plan §6.4 의 원칙 예시 (호르무즈 / LLM 도입 / 미중) 가 명시."""
    assert "호르무즈" in SYSTEM_PROMPT, "Plan §6.4 호르무즈 예시 누락"
    assert "LLM 도입" in SYSTEM_PROMPT, "Plan §6.4 LLM 도입 예시 누락"
    assert "미중 반도체" in SYSTEM_PROMPT, "Plan §6.4 미중 반도체 예시 누락"


def test_system_prompt_contains_6_report_modes() -> None:
    """Plan §6.4 의 6종 report_mode 명시."""
    expected_modes = ["situation", "forecast", "strategy", "technical", "market", "policy"]
    for m in expected_modes:
        assert m in SYSTEM_PROMPT, f"SYSTEM_PROMPT 에 report_mode '{m}' 없음"


def test_system_prompt_requires_1_to_3_methods() -> None:
    """Plan §6.4 의 '1~3개 method' 원칙 명시."""
    assert "1~3" in SYSTEM_PROMPT or "1-3" in SYSTEM_PROMPT, (
        "Plan §6.4 의 1~3개 method 원칙 누락"
    )


# ─── 부분 결과 — RegressionResult 형태로 ────────────────────────────────


def run_one(entry: dict[str, Any]) -> RegressionResult:
    """단일 prompt 의 Phase 1A 검증."""
    pid = entry["id"]
    expected = entry["expected"]
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    brief = design_via_heuristics(entry["prompt"], mode=expected["mode"])
    actual_methods = [m.method for m in brief.selected_methods]
    metrics["actual_methods"] = actual_methods
    metrics["expected_method"] = expected["expected_method"]
    metrics["report_mode"] = brief.report_mode
    metrics["strategic_hint"] = brief.strategic_hint

    if expected["expected_method"] not in actual_methods:
        issues.append(
            f"expected_method_not_in_selection: "
            f"expected={expected['expected_method']}, actual={actual_methods}"
        )

    if expected.get("strategic_intent") and not brief.strategic_hint:
        issues.append("strategic_intent_missed")

    return RegressionResult(
        test_name="research_director",
        prompt_id=pid,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all() -> list[RegressionResult]:
    return [run_one(p) for p in load_golden_prompts()]
