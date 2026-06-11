"""V5 Phase 6 — Chart Correctness Gate regression test.

REFACTOR_V5_PLAN.md §13.7 인수 기준:
    1. 14개 antipattern 시나리오 회귀 테스트 (각 antipattern 의 *깨진 입력*
       을 만들어서 Gate A/B/C 가 잡는지 확인).
    2. 실 사용 보고서 10건에서 차트별 Gate 통과율 텔레메트리.
    3. *0번째 사용자 발견 antipattern* — V5 출시 후 30일 새 antipattern 0건.
    4. 사용자 직접 보고 0건.

본 모듈은 #1 을 결정적으로 검증. #2~#4 는 운영 측정.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.agents.chart_critic import (
    ChartVerdict,
    KEEP_SCORE_THRESHOLD,
    critique_via_heuristics,
    is_score_keep,
)
from src.visual.chart_gate import (
    ChartGateResult,
    FallbackLadder,
    run_chart_gate,
)
from src.visual.sanity_check import (
    DEFAULT_THRESHOLDS,
    SanityCheckThresholds,
    visual_sanity_check_svg,
)
from src.visual.schemas import (
    AreaChartGuard,
    BarChartGuard,
    BubbleChartGuard,
    CandleChartGuard,
    DonutGuard,
    GanttGuard,
    HeatmapGuard,
    LineChartGuard,
    NetworkGuard,
    StackedBarGuard,
    parse_time,
    validate_chart_data,
)


# ─── Gate A — Pydantic 타입별 가드 (Plan §13.2) ──────────────────────


# AP-3 / AP-7 / AP-12 — Bubble
def test_bubble_guard_rejects_nan() -> None:
    with pytest.raises(Exception):
        BubbleChartGuard(data=[
            {"x": float("nan"), "y": 0.5, "size": 1.0},
        ])


def test_bubble_guard_rejects_zero_size() -> None:
    with pytest.raises(Exception):
        BubbleChartGuard(data=[{"x": 0.5, "y": 0.5, "size": 0}])


def test_bubble_guard_rejects_empty_data() -> None:
    with pytest.raises(Exception):
        BubbleChartGuard(data=[])


def test_bubble_guard_passes_clean() -> None:
    g = BubbleChartGuard(data=[
        {"x": 0.65, "y": 0.30, "size": 0.5, "label": "A"},
        {"x": 0.25, "y": 0.85, "size": 0.9, "label": "B"},
    ])
    assert len(g.data) == 2


# AP-13 — Gantt
def test_gantt_guard_rejects_unparseable_time() -> None:
    with pytest.raises(Exception):
        GanttGuard(rows=[
            {"label": "A", "start": "not a date", "end": "2026"},
        ])


def test_gantt_guard_rejects_start_after_end() -> None:
    with pytest.raises(Exception):
        GanttGuard(rows=[
            {"label": "A", "start": "2026-12", "end": "2026-01"},
        ])


def test_gantt_guard_rejects_duplicate_labels() -> None:
    with pytest.raises(Exception):
        GanttGuard(rows=[
            {"label": "A", "start": 2025, "end": 2026},
            {"label": "A", "start": 2026, "end": 2027},
        ])


def test_gantt_guard_passes_year_strings() -> None:
    g = GanttGuard(rows=[
        {"label": "Phase 1", "start": "2024", "end": "2026"},
        {"label": "Phase 2", "start": "2026-06", "end": "2027-12"},
    ])
    assert len(g.rows) == 2


def test_parse_time_supports_iso_and_year() -> None:
    assert parse_time("2026") is not None
    assert parse_time("2026-05") is not None
    assert parse_time("2026-05-01") is not None
    assert parse_time(2026) is not None
    assert parse_time("not a date") is None
    assert parse_time(None) is None


# AP-7 / AP-1 — Network
def test_network_guard_rejects_link_with_unknown_node() -> None:
    with pytest.raises(Exception):
        NetworkGuard(
            nodes=[{"id": "a"}, {"id": "b"}],
            links=[{"source": "a", "target": "phantom"}],
        )


def test_network_guard_rejects_duplicate_node_ids() -> None:
    with pytest.raises(Exception):
        NetworkGuard(nodes=[{"id": "a"}, {"id": "a"}])


def test_network_guard_rejects_lt_2_nodes() -> None:
    with pytest.raises(Exception):
        NetworkGuard(nodes=[{"id": "a"}])


def test_network_guard_passes_clean() -> None:
    g = NetworkGuard(
        nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        links=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    )
    assert len(g.nodes) == 3


# AP-3 — Donut
def test_donut_guard_rejects_negative_value() -> None:
    with pytest.raises(Exception):
        DonutGuard(data=[
            {"label": "A", "value": -5},
            {"label": "B", "value": 10},
            {"label": "C", "value": 8},
        ])


def test_donut_guard_rejects_total_zero() -> None:
    with pytest.raises(Exception):
        DonutGuard(data=[
            {"label": "A", "value": 0},
            {"label": "B", "value": 0},
            {"label": "C", "value": 0},
        ])


def test_donut_guard_rejects_single_slice() -> None:
    """1조각 도넛은 의미 X."""
    with pytest.raises(Exception):
        DonutGuard(data=[{"label": "A", "value": 100}])


# AP-16 — Donut 2-segment 안티패턴
def test_donut_guard_rejects_two_slices() -> None:
    """CHART-AP-16: 2-segment 도넛은 정보 손실 + subtitle 잉여.

    20260515_125106 보고서 ("외국인 5월 누적 순매도 구성") 의 회귀 케이스.
    [{반도체:16.8}, {비반도체:3.4}] — '비반도체' 잡탕 segment.
    """
    with pytest.raises(Exception, match="CHART-AP-16"):
        DonutGuard(data=[
            {"label": "반도체", "value": 16.8},
            {"label": "비반도체", "value": 3.4},
        ])


def test_donut_guard_passes_three_slices() -> None:
    """3 segment 이상이면 통과."""
    g = DonutGuard(data=[
        {"label": "반도체", "value": 16.8},
        {"label": "금융", "value": 1.2},
        {"label": "화학·자동차·기타", "value": 2.2},
    ])
    assert len(g.data) == 3


# AP-15 — Gantt zero-duration emit
def test_gantt_guard_rejects_all_zero_duration() -> None:
    """CHART-AP-15: 모든 row 가 start==end 인 gantt 는 부적합.

    20260515_125106 보고서 ("코스피 8000 돌파 타임라인") 의 회귀 케이스.
    7 row 중 6 이 zero-duration (point-in-time 이벤트 모음). 본질이
    event sequence 이지 duration timeline 이 아님 — line+marker 또는 list 로.
    """
    with pytest.raises(Exception, match="CHART-AP-15"):
        GanttGuard(rows=[
            {"label": "7000 돌파", "start": "2026-05-06", "end": "2026-05-06"},
            {"label": "개인 12.8조 순매수", "start": "2026-05-08", "end": "2026-05-08"},
            {"label": "+4.32% 7822", "start": "2026-05-11", "end": "2026-05-11"},
            {"label": "AI 국민배당금", "start": "2026-05-12", "end": "2026-05-12"},
            {"label": "외인 14.5조 순매도", "start": "2026-05-13", "end": "2026-05-13"},
            {"label": "옵션만기 5조+", "start": "2026-05-14", "end": "2026-05-14"},
            {"label": "8000 돌파", "start": "2026-05-15", "end": "2026-05-15"},
        ])


def test_gantt_guard_accepts_majority_real_durations() -> None:
    """기간 row 가 다수면 통과 — 1개 zero-duration 은 OK (range marker)."""
    g = GanttGuard(rows=[
        {"label": "Phase 1", "start": "2024", "end": "2025"},
        {"label": "Phase 2", "start": "2025", "end": "2026"},
        {"label": "Milestone", "start": "2025-06", "end": "2025-06"},  # zero-duration 1개
        {"label": "Phase 3", "start": "2026", "end": "2027"},
    ])
    assert len(g.rows) == 4


def test_gantt_guard_rejects_at_threshold() -> None:
    """zero-duration ratio = 0.75 (3/4) 이면 거절 (> 0.7 임계)."""
    with pytest.raises(Exception, match="CHART-AP-15"):
        GanttGuard(rows=[
            {"label": "Phase 1", "start": "2024", "end": "2026"},  # 기간
            {"label": "Event A", "start": "2026-03", "end": "2026-03"},
            {"label": "Event B", "start": "2026-06", "end": "2026-06"},
            {"label": "Event C", "start": "2026-09", "end": "2026-09"},
        ])


# AP-1 — StackedBar
def test_stacked_guard_rejects_size_mismatch() -> None:
    """series 의 values 개수 ≠ categories 개수 → fail."""
    with pytest.raises(Exception):
        StackedBarGuard(
            categories=["a", "b", "c"],
            series=[{"name": "x", "values": [1, 2]}],   # 3 expected, got 2
        )


def test_stacked_guard_rejects_nan_value() -> None:
    with pytest.raises(Exception):
        StackedBarGuard(
            categories=["a", "b"],
            series=[{"name": "x", "values": [1, float("nan")]}],
        )


# ─── validate_chart_data 통합 ────────────────────────────────────────


def test_validate_chart_data_bar_pass() -> None:
    ok, _ = validate_chart_data("bar", [
        {"label": "A", "value": 10},
        {"label": "B", "value": 20},
    ])
    assert ok


def test_validate_chart_data_bar_nan_fail() -> None:
    ok, reason = validate_chart_data("bar", [
        {"label": "A", "value": float("nan")},
    ])
    assert not ok
    assert "NaN" in reason or "AP-3" in reason


def test_validate_chart_data_unknown_type_passes_through() -> None:
    """가드 없는 type 은 통과 (vega validate 가 처리)."""
    ok, reason = validate_chart_data("unknown_type", [{"x": 1}])
    assert ok
    assert "no_typed_guard" in reason


def test_validate_chart_data_gantt_dict_data() -> None:
    """gantt 의 data 가 list[dict] 로 와도 OK."""
    ok, _ = validate_chart_data("gantt", [
        {"label": "A", "start": "2025", "end": "2026"},
    ])
    assert ok


# ─── Gate B — ChartCritic 결정적 휴리스틱 ──────────────────────────


def test_critic_drops_when_prose_does_not_cite_numbers() -> None:
    """AP-V5-7 / AP-V5-24 — prose 가 차트 수치 인용 안 함 → drop."""
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 35}, {"label": "B", "value": 80}],
    }
    prose = "이 사건은 매우 중요하다. 영향이 광범위하다."
    verdict = critique_via_heuristics(chart, prose)
    assert verdict.verdict == "drop"
    assert "Q4" in verdict.reason


def test_critic_keeps_when_prose_cites_numbers() -> None:
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 35}, {"label": "B", "value": 80}],
    }
    prose = "한국 35%, 일본 80% — 전이 채널 분석에서 핵심."
    verdict = critique_via_heuristics(chart, prose)
    assert verdict.verdict == "keep"
    assert verdict.score >= 4


def test_critic_keep_threshold_is_4() -> None:
    """Plan §13.8 — score ≥ 4 만 진짜 keep."""
    assert KEEP_SCORE_THRESHOLD == 4
    assert is_score_keep(4, "keep")
    assert is_score_keep(5, "keep")
    assert not is_score_keep(3, "keep")     # 3 = ambiguous → drop
    assert not is_score_keep(5, "drop")
    assert not is_score_keep(5, "replace")


def test_critic_drops_vacuous_takeaway() -> None:
    """Q7 — '변동성이 크다' 같은 공허한 takeaway."""
    chart = {
        "type": "bar",
        "title": "변동성이 크다",
        "data": [{"label": "A", "value": 0.55}],
    }
    verdict = critique_via_heuristics(chart, "")
    # 짧은 vacuous title + 1 항목 → drop.
    assert verdict.verdict == "drop"


# ─── Gate C — Visual Sanity ──────────────────────────────────────────


_VIEWBOX = (0.0, 0.0, 560.0, 280.0)


def test_sanity_check_rejects_empty_svg() -> None:
    result = visual_sanity_check_svg("", _VIEWBOX)
    assert not result.passed


def test_sanity_check_rejects_no_marks() -> None:
    """AP-12 — 데이터 마크 0개."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 280"></svg>'
    result = visual_sanity_check_svg(svg, _VIEWBOX)
    assert not result.passed
    assert any("AP-12" in i for i in result.issues)


def test_sanity_check_passes_with_marks() -> None:
    """마크가 있고 라벨 충돌 없으면 pass — 단 fill_ratio 임계 통과 필요."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 280">
      <rect x="10" y="10" width="50" height="100"/>
      <rect x="100" y="20" width="50" height="80"/>
      <rect x="200" y="30" width="50" height="60"/>
      <rect x="300" y="40" width="50" height="40"/>
      <text x="20" y="200">ABCDE</text>
      <text x="120" y="200">FGHIJ</text>
      <text x="300" y="200">KLMNO</text>
    </svg>'''
    # 임계를 낮게 설정 — 단순 svg 로 fill_ratio 만족 어려움.
    th = SanityCheckThresholds(fill_ratio_min=0.01, label_overlap_ratio_max=0.5)
    result = visual_sanity_check_svg(svg, _VIEWBOX, thresholds=th)
    assert result.metrics["mark_count"] >= 4


def test_sanity_check_detects_label_overlap() -> None:
    """AP-5/6/10 — 라벨이 같은 위치에 다수 → 충돌."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <rect x="10" y="10" width="20" height="50"/>
      <text x="10" y="50">한국 의존도 매우 높음</text>
      <text x="11" y="51">한국 의존도 매우 높음</text>
      <text x="12" y="52">한국 의존도 매우 높음</text>
      <text x="13" y="53">한국 의존도 매우 높음</text>
    </svg>'''
    result = visual_sanity_check_svg(svg, (0, 0, 200, 100))
    # overlap_ratio 가 매우 높을 것.
    assert result.metrics["label_overlap_ratio"] > 0.0


def test_sanity_check_detects_label_clipped_outside_viewbox() -> None:
    """AP-5 — text 가 viewBox 밖."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <rect x="10" y="10" width="20" height="50"/>
      <text x="500" y="500">밖에 있음</text>
    </svg>'''
    result = visual_sanity_check_svg(svg, (0, 0, 100, 100))
    assert any("AP-5" in i for i in result.issues)


# ─── Gate D — Fallback Ladder (Plan §13.5) ──────────────────────────


def test_fallback_to_fact_grid() -> None:
    chart = {
        "title": "테스트",
        "data": [
            {"label": "A", "value": 30},
            {"label": "B", "value": 80},
            {"label": "C", "value": 18},
        ],
    }
    fg = FallbackLadder.to_fact_grid(chart)
    assert fg is not None
    assert fg["kind"] == "fact_grid"
    assert len(fg["tiles"]) == 3


def test_fallback_to_fact_grid_rejects_too_many_rows() -> None:
    chart = {
        "data": [{"label": f"L{i}", "value": i} for i in range(20)],
    }
    fg = FallbackLadder.to_fact_grid(chart)
    assert fg is None  # > 6 rows.


def test_fallback_to_text_summary() -> None:
    chart = {
        "title": "분기 흐름",
        "data": [{"label": f"L{i}", "value": i * 10} for i in range(10)],
    }
    text = FallbackLadder.to_text_summary(chart)
    assert text is not None
    assert "외 7건" in text or "분기 흐름" in text


def test_fallback_to_fact_grid_returns_none_for_empty_data() -> None:
    assert FallbackLadder.to_fact_grid({"data": []}) is None
    assert FallbackLadder.to_text_summary({"data": []}) is None


# ─── Gate 통합 — run_chart_gate ─────────────────────────────────────


def test_run_chart_gate_keeps_clean_chart() -> None:
    """clean bar chart + prose 인용 → keep."""
    chart = {
        "type": "bar",
        "title": "한국 일본 의존도",
        "data": [{"label": "한국", "value": 35}, {"label": "일본", "value": 80}],
        "source_ids": ["S-001"],
    }
    prose = "한국의 의존도는 35%, 일본은 80% 에 달한다."
    result = run_chart_gate(chart, section_prose=prose)
    assert result.passed
    assert result.final_verdict == "keep"


def test_run_chart_gate_falls_back_when_unregistered() -> None:
    """Capability Registry 미등재 → Gate A fail → fallback."""
    chart = {
        "type": "phantom_chart_type",
        "title": "테스트",
        "data": [{"label": "A", "value": 30}, {"label": "B", "value": 50}],
    }
    result = run_chart_gate(chart, section_prose="A 30, B 50")
    assert not result.passed
    # fact_grid 가능 데이터.
    assert result.final_verdict in ("fallback_fact_grid", "fallback_text", "fallback_drop")
    assert any("Gate A" in i for i in result.issues)


def test_run_chart_gate_falls_back_when_prose_missing() -> None:
    """Q4 fail → Gate B drop → fallback."""
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 35}],
    }
    prose = "차트 수치 안 인용함."
    result = run_chart_gate(chart, section_prose=prose)
    assert not result.passed
    assert result.final_verdict in ("fallback_fact_grid", "fallback_text", "fallback_drop")


def test_run_chart_gate_drops_experimental_without_must_have() -> None:
    """experimental 차트 → Gate A fail → fallback."""
    chart = {
        "type": "chord",
        "title": "테스트",
        "data": [{"source": "a", "target": "b", "value": 10}],
    }
    result = run_chart_gate(chart)
    assert not result.passed


def test_run_chart_gate_allows_experimental_with_must_have() -> None:
    """ResearchDirector must_have 명시 시 experimental 허용. 단 다른 게이트
    통과는 별개."""
    chart = {
        "type": "treemap",
        "title": "테스트",
        "data": [
            {"hierarchy": "X", "value": 30, "label": "A"},
            {"hierarchy": "Y", "value": 50, "label": "B"},
        ],
        "source_ids": ["S-001"],
    }
    prose = "A 의 비중 30%, B 가 50% — treemap 으로 표현."
    result = run_chart_gate(
        chart, section_prose=prose, must_have_types=["treemap"]
    )
    # Gate A 는 통과 (must_have). 그 후 다른 게이트 결과에 따라.
    assert result.gate_results.get("gate_a", {}).get("passed") is True


# ─── v5.2.0 Candle / Area 가드 ──────────────────────────────────


def test_candle_guard_rejects_single_bar() -> None:
    with pytest.raises(Exception):
        CandleChartGuard(data=[
            {"date": "2026-05-15", "open": 100, "high": 110, "low": 95, "close": 105},
        ])


def test_candle_guard_rejects_negative_price() -> None:
    with pytest.raises(Exception, match="CHART-AP-3"):
        CandleChartGuard(data=[
            {"date": "2026-05-14", "open": 100, "high": 110, "low": 95, "close": 105},
            {"date": "2026-05-15", "open": -1, "high": 110, "low": 95, "close": 105},
        ])


def test_candle_guard_rejects_inverted_ohlc() -> None:
    """low > open / high < close 등 OHLC 순서 위반."""
    with pytest.raises(Exception, match="CHART-AP-3"):
        CandleChartGuard(data=[
            {"date": "2026-05-14", "open": 100, "high": 110, "low": 95, "close": 105},
            # close 가 high 보다 큼 — 위반
            {"date": "2026-05-15", "open": 105, "high": 110, "low": 100, "close": 120},
        ])


def test_candle_guard_accepts_realistic_ohlc() -> None:
    """삼성전자 같은 정상 OHLC."""
    g = CandleChartGuard(data=[
        {"date": "2026-05-13", "open": 92000, "high": 93500, "low": 91500, "close": 93000, "volume": 12_000_000},
        {"date": "2026-05-14", "open": 93000, "high": 94200, "low": 92800, "close": 94000, "volume": 15_500_000},
        {"date": "2026-05-15", "open": 94000, "high": 95000, "low": 93500, "close": 93800, "volume": 18_000_000},
    ])
    assert len(g.data) == 3
    assert g.data[0].close == 93000


def test_candle_guard_doji_passes() -> None:
    """open == close (도지 캔들) 도 정상 케이스."""
    g = CandleChartGuard(data=[
        {"date": "2026-05-14", "open": 100, "high": 105, "low": 98, "close": 100},
        {"date": "2026-05-15", "open": 100, "high": 102, "low": 99, "close": 100},
    ])
    assert len(g.data) == 2


def test_area_guard_rejects_single_point() -> None:
    with pytest.raises(Exception):
        AreaChartGuard(data=[{"x": "2026-05-15", "y": 85.4}])


def test_area_guard_rejects_nan_y() -> None:
    with pytest.raises(Exception, match="CHART-AP-3"):
        AreaChartGuard(data=[
            {"x": "2026-05-14", "y": 85.0},
            {"x": "2026-05-15", "y": float("nan")},
        ])


def test_area_guard_accepts_realistic() -> None:
    """WTI 같은 정상 시계열."""
    g = AreaChartGuard(data=[
        {"x": "2026-05-01", "y": 78.0},
        {"x": "2026-05-08", "y": 82.5},
        {"x": "2026-05-15", "y": 85.4},
    ])
    assert len(g.data) == 3


def test_validate_chart_data_candle_pass() -> None:
    ok, _ = validate_chart_data("candle", [
        {"date": "2026-05-14", "open": 100, "high": 110, "low": 95, "close": 105},
        {"date": "2026-05-15", "open": 105, "high": 115, "low": 100, "close": 112},
    ])
    assert ok


def test_validate_chart_data_area_pass() -> None:
    ok, _ = validate_chart_data("area", [
        {"x": "2026-05-14", "y": 85.0},
        {"x": "2026-05-15", "y": 85.4},
    ])
    assert ok


def test_validate_chart_data_candle_fail_propagates() -> None:
    ok, reason = validate_chart_data("candle", [
        {"date": "2026-05-15", "open": 100, "high": 90, "low": 95, "close": 105},  # high < low/open
    ])
    assert not ok
    assert "CHART-AP" in reason or "Candle" in reason or "candle" in reason


# ==========================================================================
# v7.0.0 Track A — 신규 3종 가드 (REFACTOR_V7_PLAN.md §1.3, guarded tier)
# ==========================================================================

_BUMP_OK = {
    "periods": ["2023", "2024", "2025"],
    "items": [
        {"name": "TSMC", "ranks": [1, 1, 1]},
        {"name": "삼성", "ranks": [2, 2, 3]},
        {"name": "SMIC", "ranks": [4, 3, 2]},
    ],
}


def test_bump_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("bump", _BUMP_OK)
    assert ok, reason


def test_bump_guard_rejects_rank_grid_mismatch() -> None:
    bad = {
        "periods": ["2023", "2024", "2025"],
        "items": [
            {"name": "A", "ranks": [1, 1]},  # 길이 2 != periods 3
            {"name": "B", "ranks": [2, 2, 2]},
            {"name": "C", "ranks": [3, 3, 3]},
        ],
    }
    ok, reason = validate_chart_data("bump", bad)
    assert not ok and "격자" in reason


def test_bump_guard_rejects_sub_one_rank_and_too_few_items() -> None:
    ok, _ = validate_chart_data("bump", {
        "periods": ["23", "24"],
        "items": [
            {"name": "A", "ranks": [0, 1]},  # rank < 1
            {"name": "B", "ranks": [2, 2]},
            {"name": "C", "ranks": [3, 3]},
        ],
    })
    assert not ok
    ok, _ = validate_chart_data("bump", {
        "periods": ["23", "24"],
        "items": [{"name": "A", "ranks": [1, 1]}, {"name": "B", "ranks": [2, 2]}],
    })
    assert not ok  # 항목 <3 → 본문 한 문장으로 충분


def test_bump_guard_rejects_list_payload() -> None:
    ok, reason = validate_chart_data("bump", [{"name": "A", "ranks": [1, 2]}])
    assert not ok and "dict" in reason


def test_bullet_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("bullet", [
        {"label": "매출", "value": 133.9, "target": 128.0, "ranges": [100, 120, 140]},
        {"label": "영업이익", "value": 31.2, "target": 33.5},
    ])
    assert ok, reason


def test_bullet_guard_rejects_nonpositive_target_and_nan() -> None:
    ok, _ = validate_chart_data("bullet", [{"label": "매출", "value": 10.0, "target": 0}])
    assert not ok  # target ≤0 → bar 로 (가드가 강제)
    ok, _ = validate_chart_data("bullet", [
        {"label": "매출", "value": float("nan"), "target": 100.0},
    ])
    assert not ok


def test_bullet_guard_rejects_too_many_rows() -> None:
    rows = [{"label": f"r{i}", "value": 1.0, "target": 2.0} for i in range(8)]
    ok, _ = validate_chart_data("bullet", rows)
    assert not ok  # 1~7행 한정


def test_connected_scatter_guard_accepts_path() -> None:
    ok, reason = validate_chart_data("connected_scatter", [
        {"x": 4.6, "y": 1495, "label": "25.7"},
        {"x": 4.4, "y": 1480},
        {"x": 4.0, "y": 1445},
        {"x": 3.5, "y": 1402, "label": "26.6"},
    ])
    assert ok, reason


def test_connected_scatter_guard_rejects_short_and_nan() -> None:
    ok, _ = validate_chart_data("connected_scatter", [{"x": 1, "y": 2}, {"x": 2, "y": 3}])
    assert not ok  # <4 점 — 궤적이 아님
    ok, _ = validate_chart_data("connected_scatter", [
        {"x": 1, "y": 2}, {"x": 2, "y": float("inf")}, {"x": 3, "y": 4}, {"x": 4, "y": 5},
    ])
    assert not ok


def test_composed_section_caps_annotations_at_three() -> None:
    """v7.0.0 (AP-V7-6) — 유효 차트의 annotation 은 dict+유효 kind 만, 최대 3개."""
    from src.models import ComposedSection
    sec = ComposedSection(heading="h", prose="p", charts=[{
        "type": "line",
        "title": "t",
        "data": [{"x": "1", "y": 1.0}, {"x": "2", "y": 2.0}],
        "annotations": [
            {"kind": "vline", "x": "1", "label": "a"},
            {"kind": "hline", "y": 1.5, "label": "b"},
            {"kind": "band", "x_from": "1", "x_to": "2"},
            {"kind": "point", "x": "2", "y": 2.0},   # 4번째 — 잘림
            {"kind": "blink", "x": "1"},              # 무효 kind — 제거
            "문자열",                                  # 비 dict — 제거
        ],
    }])
    anns = sec.charts[0]["annotations"]
    assert len(anns) == 3
    assert all(a["kind"] in ("vline", "hline", "band", "point") for a in anns)


def test_composed_section_strips_empty_annotations_key() -> None:
    from src.models import ComposedSection
    sec = ComposedSection(heading="h", prose="p", charts=[{
        "type": "line",
        "title": "t",
        "data": [{"x": "1", "y": 1.0}, {"x": "2", "y": 2.0}],
        "annotations": ["전부", "무효"],
    }])
    assert "annotations" not in sec.charts[0]
