"""V6 Phase V6-0 — Fact discipline fixture 로드/스키마 회귀.

REFACTOR_V6_PLAN.md §3 (Phase V6-0) + §4 (테스트 플랜 T-1 스켈레톤).

본 테스트는 V6 의 사실 거버넌스 fixture (fact_discipline_scenarios.yaml) 가
구조적으로 건강한지 검증한다. 실제 결정적 가드 (UnsourcedNumberGuard 등) 는
Phase V6-1 에서 src/factcheck/deterministic_guards.py 에 구현되며, 그때 본
파일에 검출률 테스트 (T-1) 가 추가된다.

지금 단계의 목적: error_class 5종 동결 + 시나리오 스키마 강제 + NVIDIA 회귀
케이스 영구 보존. fixture 가 깨지거나 error_class 가 임의 확장되면 fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.factcheck.deterministic_guards import (
    GuardFlag,
    nan_exposure_guard,
    run_fact_guards,
)
from src.models import ComposedReport, ComposedSection, ContextAnalysis

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "fact_discipline_scenarios.yaml"
)

# REFACTOR_V6_PLAN.md §3 Phase V6-0 에서 동결한 5종. 추가는 Plan 갱신 + 본 set
# 갱신 *동시에* 만 (AP-V6 신규 케이스 등록 절차).
# 1차 동결 5종 (REFACTOR_V6_PLAN.md §3 Phase V6-0 — NVIDIA 2026-06-01 표본).
FROZEN_ERROR_CLASSES = {
    "unsourced_number",
    "scope_misattribution",
    "novelty_conflation",
    "timepoint_overclaim",
    "list_truncation",
}

# 2차 확장 6종 (2026-06-03 일일 브리핑 표본, 사용자 게이트 승격 — AP-V6-9).
# REFACTOR_V6_PLAN.md §0.2-b. 신규 class 는 Plan §0.2-b + 본 set 갱신 *동시에* 만.
EXPANDED_ERROR_CLASSES = {
    "market_data_mismatch",
    "stale_sourcing",
    "event_conflation",
    "attribution_as_fact",
    "causal_overreach",
    "metric_label_ambiguity",
}

# 임의 확장 차단용 전체 enum (가드 대상 = 알려진 class 전체).
ALL_ERROR_CLASSES = FROZEN_ERROR_CLASSES | EXPANDED_ERROR_CLASSES

_REQUIRED_KEYS = {
    "id",
    "error_class",
    "evidence",
    "bad_prose",
    "good_prose",
    "expected_flag",
    "guard",
}
_REQUIRED_EVIDENCE_KEYS = {"fact", "source_date", "scope_note", "source_url"}


def _load() -> list[dict]:
    with FIXTURE_PATH.open(encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    return list(data.get("scenarios", []))


def test_fixture_loads_and_nonempty() -> None:
    scenarios = _load()
    assert len(scenarios) >= 5, "최소 5종 (NVIDIA 회귀) 시나리오가 있어야 한다"


def test_every_scenario_has_required_schema() -> None:
    for sc in _load():
        missing = _REQUIRED_KEYS - set(sc)
        assert not missing, f"{sc.get('id')} 에 누락된 키: {missing}"
        ev_missing = _REQUIRED_EVIDENCE_KEYS - set(sc["evidence"])
        assert not ev_missing, f"{sc['id']} evidence 누락: {ev_missing}"


def test_error_class_within_known_enum() -> None:
    for sc in _load():
        assert (
            sc["error_class"] in ALL_ERROR_CLASSES
        ), f"{sc['id']} 의 error_class '{sc['error_class']}' 가 알려진 enum 밖 (게이트 승격 필요)"


def test_all_known_error_classes_covered() -> None:
    present = {sc["error_class"] for sc in _load()}
    assert FROZEN_ERROR_CLASSES <= present, (
        "1차 동결 5종이 모두 fixture 에 1건 이상 있어야 한다. "
        f"누락: {FROZEN_ERROR_CLASSES - present}"
    )
    assert present == ALL_ERROR_CLASSES, (
        "알려진 error_class 가 모두 fixture 에 1건 이상 있어야 한다. "
        f"누락: {ALL_ERROR_CLASSES - present}"
    )


def test_scenario_ids_unique() -> None:
    ids = [sc["id"] for sc in _load()]
    assert len(ids) == len(set(ids)), "시나리오 id 중복"


def test_bad_and_good_prose_differ() -> None:
    for sc in _load():
        assert (
            sc["bad_prose"].strip() != sc["good_prose"].strip()
        ), f"{sc['id']} 의 bad/good prose 가 동일 — 교정 케이스가 아님"


# ==========================================================================
# T-1 — 결정적 사전필터 가드 검출 (Phase V6-2)
#
# 결정적으로 *명백히* 잡히는 시나리오만 가드 책임. 의미 판단이 필요한 케이스
# (unsourced_threshold[근거 산출] / event_conflation / attribution_as_fact /
# causal_overreach / metric_label_ambiguity / timepoint_overclaim[앵커 정확성] /
# list_truncation / market FX 0.29% sub-tolerance) 는 Codex critic(Phase 3) 담당.
# 본 테스트는 ① bad_prose 검출 ② good_prose 0-FP 를 둘 다 강제한다.
# ==========================================================================

_SCENARIOS_BY_ID = {sc["id"]: sc for sc in _load()}

# id → (기대 flag, 가드 부가 입력). 결정적으로 잡혀야 하는 5종.
_DETERMINISTIC_CASES = {
    "scope_misattribution_01": {"expected": "scope_bareword"},
    "unsourced_number_01": {"expected": "unsourced_number"},
    "novelty_conflation_01": {"expected": "novelty_delta", "pub": "2026-06-01"},
    "stale_sourcing_01": {"expected": "stale_relative_timepoint", "pub": "2026-06-03"},
    "market_data_mismatch_01": {
        "expected": "market_value_mismatch",
        "market": {"코스피": 8801.49},
    },
}


def _build_io(scenario: dict, prose: str, case: dict) -> tuple[ComposedReport, ContextAnalysis, dict]:
    ev = scenario["evidence"]
    report = ComposedReport(
        headline="테스트 보고서",
        sections=[ComposedSection(heading=scenario["id"], prose=prose)],
    )
    ctx = ContextAnalysis(background=ev.get("fact", ""), date=ev.get("source_date", ""))
    kwargs = {
        "publication_date": case.get("pub", ""),
        "source_dates": [ev["source_date"]] if ev.get("source_date") else [],
        "market_series": case.get("market"),
        "scope_notes": [ev["scope_note"]] if ev.get("scope_note") else [],
    }
    return report, ctx, kwargs


@pytest.mark.parametrize("scenario_id", list(_DETERMINISTIC_CASES))
def test_guard_detects_bad_prose(scenario_id: str) -> None:
    sc = _SCENARIOS_BY_ID[scenario_id]
    case = _DETERMINISTIC_CASES[scenario_id]
    report, ctx, kwargs = _build_io(sc, sc["bad_prose"], case)
    flags = {f.flag for f in run_fact_guards(report, ctx, **kwargs)}
    assert case["expected"] in flags, (
        f"{scenario_id}: bad_prose 에서 '{case['expected']}' 미검출. 검출된 것: {flags}"
    )


@pytest.mark.parametrize("scenario_id", list(_DETERMINISTIC_CASES))
def test_guard_no_false_positive_on_good_prose(scenario_id: str) -> None:
    sc = _SCENARIOS_BY_ID[scenario_id]
    case = _DETERMINISTIC_CASES[scenario_id]
    report, ctx, kwargs = _build_io(sc, sc["good_prose"], case)
    flags = {f.flag for f in run_fact_guards(report, ctx, **kwargs)}
    assert case["expected"] not in flags, (
        f"{scenario_id}: good_prose 에서 '{case['expected']}' 오검출(FP). 검출된 것: {flags}"
    )


def test_deterministic_detection_rate() -> None:
    """결정적 타깃 5종 전부 검출 (100%) — DoD ≥90% 충족 확인."""
    hits = 0
    for sid, case in _DETERMINISTIC_CASES.items():
        sc = _SCENARIOS_BY_ID[sid]
        report, ctx, kwargs = _build_io(sc, sc["bad_prose"], case)
        flags = {f.flag for f in run_fact_guards(report, ctx, **kwargs)}
        if case["expected"] in flags:
            hits += 1
    rate = hits / len(_DETERMINISTIC_CASES)
    assert rate >= 0.9, f"결정적 검출률 {rate:.0%} < 90%"


def test_duplicate_heading_guard() -> None:
    from src.factcheck.deterministic_guards import duplicate_heading_guard
    dup = ComposedReport(headline="h", sections=[
        ComposedSection(heading="시장의 첫 반응", prose="a"),
        ComposedSection(heading="생태계 확장", prose="b"),
        ComposedSection(heading="시장의 첫 반응", prose="c"),  # 중복
    ])
    flags = duplicate_heading_guard(dup)
    assert any(f.flag == "duplicate_heading" for f in flags)
    assert "시장의 첫 반응" in flags[0].quote
    # 정규화 동일(공백·구두점 차이)도 중복으로.
    near = ComposedReport(headline="h", sections=[
        ComposedSection(heading="다음 수", prose="a"),
        ComposedSection(heading="다음수", prose="b"),
    ])
    assert duplicate_heading_guard(near)
    # 중복 없으면 빈 list.
    ok = ComposedReport(headline="h", sections=[
        ComposedSection(heading="첫째", prose="a"), ComposedSection(heading="둘째", prose="b")])
    assert duplicate_heading_guard(ok) == []


def test_nan_exposure_guard() -> None:
    report = ComposedReport(
        headline="시장 브리핑",
        sections=[ComposedSection(heading="지표", prose="코스피 nan% 마감")],
    )
    flags = nan_exposure_guard([], report) + run_fact_guards(report, ContextAnalysis())
    assert any(f.flag == "nan_exposed" for f in flags)


def test_clean_report_zero_flags() -> None:
    report = ComposedReport(
        headline="평범한 보고서",
        sections=[ComposedSection(heading="개요", prose="특별한 정량 단정이 없는 본문이다.")],
    )
    ctx = ContextAnalysis(background="배경 설명", summary="요약")
    assert run_fact_guards(report, ctx) == []


def test_guard_flag_as_pre_flag_seam() -> None:
    # Phase 3 합류 seam — GuardFlag 가 codex pre_flags 한 줄로 직렬화되는지.
    flag = GuardFlag(
        guard="UnsourcedNumberGuard", flag="unsourced_number",
        location="headline", quote="27년 만", detail="근거에 없음",
    )
    line = flag.as_pre_flag()
    assert "unsourced_number" in line and "27년 만" in line
