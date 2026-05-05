"""V5 Phase 0B — Test 1/5: Golden Prompt Regression.

Plan §3.4 (가) — 20개 prompt 의 expected report mode, expected section
count range, required evidence types, forbidden chart types, required map
behavior 를 fixture 로 박는다. V5 변경이 expected 와 어긋나면 실패.

Phase 0B 시점 운용:
- ``fixtures/sample_composed_reports/<id>.json`` 이 있으면 *실제 검증*.
- 없으면 *fixture 자체의 형식 검증* + ``resolve_mode_fallback`` 만 검증.
  (사용자가 ``scripts/record_baseline.py`` 로 v4.5.7 sample 채운 후
   본격 회귀 검증 활성.)

CLI runner 와 호환되도록 모든 검증 로직은 ``run_one(...)`` 함수에 모음.
pytest 는 ``run_one`` 을 호출하기만 한다.

사용:
    python -m pytest tests/regression/test_golden_prompts.py -v
또는:
    python scripts/run_regression.py --tests golden
"""

from __future__ import annotations

from typing import Any

from tests.regression._pytest_compat import pytest

from tests.regression.helpers import (
    RegressionResult,
    collect_chart_types,
    collect_geo_legend_labels,
    has_embedded_map,
    load_golden_prompts,
    load_distribution,
    load_sample_composed_report,
    resolve_mode_fallback,
    section_count,
    total_prose_chars,
)


# ─── 코어 검증 함수 (pytest 와 CLI runner 가 공유) ───────────────────────


def run_one(prompt_entry: dict[str, Any]) -> RegressionResult:
    """단일 Golden Prompt 의 expected metadata 검증.

    sample_composed_reports/<id>.json 이 있으면 그 JSON 으로 검증.
    없으면 mode 결정 휴리스틱만 검증하고 sample_missing 메트릭 기록.
    """
    pid = prompt_entry["id"]
    expected = prompt_entry["expected"]
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    # (1) Mode 결정 — fixture 가 expected 한 mode 가 resolve_mode 에서 나오는지.
    actual_mode = resolve_mode_fallback(prompt_entry["prompt"])
    metrics["mode_actual"] = actual_mode
    metrics["mode_expected"] = expected["mode"]
    if actual_mode != expected["mode"]:
        issues.append(
            f"mode_mismatch: expected={expected['mode']}, actual={actual_mode}"
        )

    # (2) sample 보고서가 있으면 더 깊게 검증.
    sample = load_sample_composed_report(pid)
    if sample is None:
        metrics["sample_missing"] = True
        return RegressionResult(
            test_name="golden_prompts",
            prompt_id=pid,
            passed=not issues,
            issues=issues,
            metrics=metrics,
        )
    metrics["sample_missing"] = False

    # (2a) 섹션 수 범위.
    sc = section_count(sample)
    metrics["section_count"] = sc
    lo, hi = expected["section_count_range"]
    if not (lo <= sc <= hi):
        issues.append(f"section_count_out_of_range: {sc} not in [{lo},{hi}]")

    # (2b) 총 자수.
    chars = total_prose_chars(sample)
    metrics["total_prose_chars"] = chars
    if chars < expected["min_total_chars"]:
        issues.append(
            f"total_chars_below_minimum: {chars} < {expected['min_total_chars']}"
        )

    # (2c) 금지 차트 type — 사건과 부적합한 type 이 emit 되면 회귀.
    forbidden = set(expected.get("forbidden_chart_types") or [])
    actual_chart_types = collect_chart_types(sample)
    metrics["chart_types"] = sorted(actual_chart_types)
    overlap = forbidden & actual_chart_types
    if overlap:
        issues.append(
            f"forbidden_chart_types_emitted: {sorted(overlap)}"
        )

    # (2d) 지도 동작.
    map_rules = expected.get("required_map_behavior") or {}
    has_map = has_embedded_map(sample)
    metrics["has_map"] = has_map
    if map_rules.get("must_have_map") and not has_map:
        issues.append("must_have_map: embedded_map missing")
    if map_rules.get("forbidden_map") and has_map:
        issues.append("forbidden_map: embedded_map should not be emitted")

    forbidden_geo = set(map_rules.get("forbidden_geo_annotations") or [])
    if forbidden_geo and has_map:
        labels = collect_geo_legend_labels(sample)
        bad = forbidden_geo & labels
        if bad:
            issues.append(
                f"forbidden_geo_annotations_present: {sorted(bad)} (CHART-AP-14 회귀)"
            )

    # (2e) contradictions / watch_signals 강제.
    if expected.get("must_have_contradictions") and not (sample.get("contradictions") or []):
        issues.append("must_have_contradictions: contradictions empty")
    if expected.get("must_have_watch_signals") and not (sample.get("watch_signals") or []):
        issues.append("must_have_watch_signals: watch_signals empty")

    return RegressionResult(
        test_name="golden_prompts",
        prompt_id=pid,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all() -> list[RegressionResult]:
    """모든 Golden Prompt 에 대해 run_one 실행. CLI runner 진입점."""
    return [run_one(p) for p in load_golden_prompts()]


# ─── pytest 통합 ────────────────────────────────────────────────────────


def test_distribution_matches_plan_3_3() -> None:
    """Plan §3.3 의 8개 카테고리 분포가 fixture 와 일치하는지."""
    dist = load_distribution()
    expected_dist = {
        "geopolitical_forecast": 3,
        "financial_transmission": 3,
        "tech_structural": 3,
        "policy_decision": 2,
        "strategic_query": 3,
        "map_required": 2,
        "no_charts": 2,
        "long_deep_truncation": 2,
    }
    assert dist == expected_dist, (
        f"distribution drift from REFACTOR_V5_PLAN.md §3.3: "
        f"expected={expected_dist}, actual={dist}"
    )


def test_total_prompt_count_is_20() -> None:
    """Plan §3.3 의 '20건' 강제."""
    prompts = load_golden_prompts()
    assert len(prompts) == 20, f"expected 20 prompts, found {len(prompts)}"


def test_each_prompt_has_required_keys() -> None:
    """fixture 형식 가드 — 각 prompt 가 필수 키 모두 가지는지."""
    required_top = {"id", "category", "prompt", "expected"}
    required_expected = {
        "mode", "section_count_range", "required_evidence_types",
        "forbidden_chart_types", "required_map_behavior",
        "min_total_chars", "must_have_contradictions",
        "must_have_watch_signals", "expected_method", "strategic_intent",
    }
    for p in load_golden_prompts():
        missing_top = required_top - set(p.keys())
        assert not missing_top, f"{p.get('id')}: missing top-level keys {missing_top}"
        missing_exp = required_expected - set((p["expected"] or {}).keys())
        assert not missing_exp, f"{p['id']}: missing expected.* keys {missing_exp}"


def test_each_expected_method_is_in_phase_1a_enum() -> None:
    """Phase 1A — expected_method 가 src/state/models.py:AnalysisMethod 의 9종 안에 있는지.

    fixture 가 enum 외 method 를 박으면 ResearchDirector 가 절대 emit 할 수 없어
    Plan §6.6 #4 (≥80% 일치) 가 무의미해진다. SSOT drift 차단.
    """
    expected_enum = {
        "ACH", "scenario_tree", "transmission_channel", "stakeholder_matrix",
        "fault_tree", "decision_matrix", "pre_mortem",
        "transmission_timeline", "comparative",
    }
    for p in load_golden_prompts():
        m = (p.get("expected") or {}).get("expected_method", "")
        assert m in expected_enum, (
            f"{p['id']}: expected_method={m!r} not in Phase 1A 9-enum {sorted(expected_enum)}"
        )


def test_distribution_matches_actual_count() -> None:
    """fixture 의 distribution 섹션이 실제 prompt 들의 카테고리 분포와 정합."""
    prompts = load_golden_prompts()
    actual: dict[str, int] = {}
    for p in prompts:
        actual[p["category"]] = actual.get(p["category"], 0) + 1
    declared = load_distribution()
    assert actual == declared, (
        f"declared distribution ({declared}) != actual count ({actual})"
    )


@pytest.mark.parametrize("entry", load_golden_prompts(), ids=lambda e: e["id"])
def test_mode_resolution(entry: dict[str, Any]) -> None:
    """resolve_mode 휴리스틱이 expected mode 와 일치하는지 (sample 무관 — 항상 검증)."""
    actual = resolve_mode_fallback(entry["prompt"])
    assert actual == entry["expected"]["mode"], (
        f"{entry['id']}: mode_mismatch — "
        f"expected={entry['expected']['mode']}, actual={actual}, "
        f"prompt={entry['prompt']!r}"
    )


@pytest.mark.parametrize("entry", load_golden_prompts(), ids=lambda e: e["id"])
def test_full_regression_when_sample_present(entry: dict[str, Any]) -> None:
    """sample 이 있는 prompt 만 전체 expected 검증.

    sample 미녹화 prompt 는 SKIP — Phase 0B 시점엔 거의 모두 SKIP 이고,
    사용자가 ``record_baseline.py`` 로 sample 채운 후 본격 활성.
    """
    if load_sample_composed_report(entry["id"]) is None:
        pytest.skip(f"{entry['id']}: sample_composed_reports/<id>.json 미녹화")
    result = run_one(entry)
    assert result.passed, (
        f"{entry['id']}: golden prompt regression failed — "
        + "; ".join(result.issues)
    )
