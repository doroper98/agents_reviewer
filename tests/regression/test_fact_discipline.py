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
    market_anchor_coherence_guard,
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

# 3차 확장 1종 (V7 Track C, 사용자 게이트 승인 2026-06-11 — REFACTOR_V7_PLAN.md §3.4).
# "사실로서 정확하지만 보고서 기준 시점과 다른 날짜의 값" (6/1↔6/5 회귀).
V7_ERROR_CLASSES = {
    "wrong_timeframe",
}

# 임의 확장 차단용 전체 enum (가드 대상 = 알려진 class 전체).
ALL_ERROR_CLASSES = FROZEN_ERROR_CLASSES | EXPANDED_ERROR_CLASSES | V7_ERROR_CLASSES

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
    # ★ 실제 회귀 — 섹션 제목 = 쟁점(모순) 섹션 제목(contradictions_heading) 중복.
    real = ComposedReport(
        headline="h",
        contradictions_heading="임대업인가, 궤도로 가는 다리인가",
        sections=[
            ComposedSection(heading="임대업인가, 궤도로 가는 다리인가", prose="a"),
            ComposedSection(heading="감시 신호", prose="b"),
        ],
    )
    rflags = duplicate_heading_guard(real)
    assert rflags and "쟁점 섹션" in rflags[0].detail
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


# ==========================================================================
# V7 Track C — 기준시점 가드 (REFACTOR_V7_PLAN.md §3.2, AP-V7-5)
#
# 날짜 비앵커 검증 회귀 차단: "수치가 어느 날짜든 맞으면 통과" 금지. ① 날짜가
# 명시된 시장 수치는 *그 날짜의* bar 와 대조 (date_anchor_mismatch) ② 종목별 최신
# 인용 시점이 가용 시계열보다 1거래일 초과 뒤처지면 stale_anchor. 둘 다 ref_frame
# opt-in — 디폴트 OFF 경로는 기존 run_fact_guards 와 byte-equal.
# ==========================================================================

_V7_BARS = {
    "코스피": [
        {"date": "2026-06-01", "close": 2901.50},
        {"date": "2026-06-02", "close": 2920.00},
        {"date": "2026-06-03", "close": 2935.40},
        {"date": "2026-06-04", "close": 2948.12},
    ],
}


def _v7_report(prose: str) -> ComposedReport:
    return ComposedReport(
        headline="일일 브리핑",
        sections=[ComposedSection(heading="시장", prose=prose)],
    )


def test_stale_anchor_guard_detects_old_citation() -> None:
    """6/4 종가가 가용한데 본문 최신 인용이 6/1 → stale_anchor (wrong_timeframe_01)."""
    sc = _SCENARIOS_BY_ID["wrong_timeframe_01"]
    flags = run_fact_guards(
        _v7_report(sc["bad_prose"]), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert any(f.flag == "stale_anchor" for f in flags), {f.flag for f in flags}


def test_stale_anchor_guard_passes_latest_citation() -> None:
    """최신 가용 일자(6/4) 인용 (good_prose) → 0-FP."""
    sc = _SCENARIOS_BY_ID["wrong_timeframe_01"]
    flags = run_fact_guards(
        _v7_report(sc["good_prose"]), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert not any(f.flag in ("stale_anchor", "date_anchor_mismatch") for f in flags)


# ==========================================================================
# v7.9.16 — MarketAnchorCoherenceGuard (kospi-date-mismatch + wrong-year)
# 데이터 계층 결정적 검출. base 가드라 fact_guards 켜지면 자동 합류 (log-only).
# ==========================================================================


def _ctx_with_series(series: list[dict], date: str = "2026-06-19") -> ContextAnalysis:
    return ContextAnalysis(date=date, time_series=series)


def test_anchor_coherence_detects_kospi_date_lag() -> None:
    """코스피만 6/17, 삼성전자 6/18 → stale_market_anchor (실제 회귀 재현)."""
    ctx = _ctx_with_series([
        {"instrument": "코스피", "source": "YAHOO", "data": [
            {"date": "2026-06-16", "close": 8726.6},
            {"date": "2026-06-17", "close": 8864.24},
        ]},
        {"instrument": "삼성전자", "source": "KRX", "data": [
            {"date": "2026-06-17", "close": 346500},
            {"date": "2026-06-18", "close": 362500},
        ]},
    ])
    flags = market_anchor_coherence_guard(ctx, publication_date="2026-06-19")
    stale = [f for f in flags if f.flag == "stale_market_anchor"]
    assert len(stale) == 1 and stale[0].location == "코스피"
    assert stale[0].severity == "high"


def test_anchor_coherence_clean_when_dates_match() -> None:
    """모든 한국거래소 지표가 같은 6/18 → 0-FP."""
    ctx = _ctx_with_series([
        {"instrument": "코스피", "source": "KRX", "data": [
            {"date": "2026-06-17", "close": 8864.24},
            {"date": "2026-06-18", "close": 9063.84},
        ]},
        {"instrument": "삼성전자", "source": "KRX", "data": [
            {"date": "2026-06-18", "close": 362500},
        ]},
    ])
    assert market_anchor_coherence_guard(ctx, publication_date="2026-06-19") == []


def test_anchor_coherence_detects_wrong_year() -> None:
    """최신 봉이 작년(2025-06-18)인데 발행은 2026 → wrong_year_market_anchor."""
    ctx = _ctx_with_series([
        {"instrument": "코스피", "source": "YAHOO", "data": [
            {"date": "2025-06-17", "close": 2880.0},
            {"date": "2025-06-18", "close": 2901.0},
        ]},
    ])
    flags = market_anchor_coherence_guard(ctx, publication_date="2026-06-19")
    assert any(f.flag == "wrong_year_market_anchor" for f in flags), {f.flag for f in flags}


def test_anchor_coherence_runs_under_base_guards() -> None:
    """run_fact_guards(base=True) 경로에 자동 합류하는지 (production wiring)."""
    ctx = _ctx_with_series([
        {"instrument": "코스피", "source": "YAHOO", "data": [
            {"date": "2026-06-17", "close": 8864.24}]},
        {"instrument": "SK하이닉스", "source": "KRX", "data": [
            {"date": "2026-06-18", "close": 2685000}]},
    ])
    report = ComposedReport(headline="브리핑", sections=[ComposedSection(heading="시장", prose="")])
    flags = run_fact_guards(report, ctx, publication_date="2026-06-19", base=True)
    assert any(f.flag == "stale_market_anchor" for f in flags), {f.flag for f in flags}


def test_stale_anchor_allows_one_bar_lag() -> None:
    """직전 거래일(6/3) 인용은 1-bar lag 허용 — 작성 중 당일 종가 미반영 보호."""
    flags = run_fact_guards(
        _v7_report("6월 3일 코스피는 2,935.40으로 마감했다"), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert not any(f.flag == "stale_anchor" for f in flags)


def test_stale_anchor_respects_newest_mention() -> None:
    """과거 회고 + 더 최신 인용이 공존하면 종목별 최댓값으로 판정 → 0-FP."""
    prose = (
        "6월 1일 코스피는 2,901.50에서 출발했지만, 6월 4일 코스피는 2,948.12로 마감하며 "
        "한 주를 강세로 마무리했다"
    )
    flags = run_fact_guards(
        _v7_report(prose), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert not any(f.flag == "stale_anchor" for f in flags)


def test_date_anchor_mismatch_detects_value_from_other_date() -> None:
    """'6월 1일 코스피 2,948.12' — 값은 6/4 종가 (다른 날짜의 정확한 값) → flag."""
    flags = run_fact_guards(
        _v7_report("6월 1일 코스피는 2,948.12로 마감했다"), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert any(f.flag == "date_anchor_mismatch" for f in flags), {f.flag for f in flags}


def test_date_anchor_passes_correct_dated_value() -> None:
    """'6월 1일 코스피 2,901.50' — 그 날짜의 실제 종가 → date_anchor 0-FP
    (시점 선택 문제는 stale_anchor 가 따로 잡는다)."""
    flags = run_fact_guards(
        _v7_report("6월 1일 코스피는 2,901.50으로 마감했다"), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
        base=False, ref_frame=True,
    )
    assert not any(f.flag == "date_anchor_mismatch" for f in flags)


def test_ref_frame_off_is_inert() -> None:
    """ref_frame=False (디폴트) 면 bad_prose 라도 V7 가드 미작동 — byte-equal 경로."""
    sc = _SCENARIOS_BY_ID["wrong_timeframe_01"]
    flags = run_fact_guards(
        _v7_report(sc["bad_prose"]), ContextAnalysis(),
        publication_date="2026-06-05", market_bars=_V7_BARS,
    )
    assert not any(f.flag in ("stale_anchor", "date_anchor_mismatch") for f in flags)


def test_reference_frame_builder() -> None:
    """build_reference_frame — 종목별 최신 가용 일자·종가·전일대비 추출, 빈 입력 inert."""
    from src.factcheck.reference_frame import build_reference_frame
    ctx = ContextAnalysis(
        time_series=[
            {"instrument": "코스피", "data": _V7_BARS["코스피"]},
            {"name": "환율", "data": []},  # 빈 시계열은 제외
        ],
    )
    frame = build_reference_frame(ctx)
    assert frame["instruments"] == [
        {
            "name": "코스피",
            "last_available_date": "2026-06-04",
            "last_close": 2948.12,
            "last_day_change_pct": 0.43,
        }
    ]
    assert build_reference_frame(ContextAnalysis()) == {"instruments": []}


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
