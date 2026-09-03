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


# CHART-AP-36 — network(행위자 관계도) 포맷 폐기. validate_chart_data 가 무조건 drop.
def test_network_chart_type_is_rejected() -> None:
    ok, reason = validate_chart_data(
        "network",
        {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"source": "a", "target": "b"}]},
    )
    assert not ok
    assert "CHART-AP-36" in reason


# CHART-AP-38 — stakeholder_map(르포 관계도)이 dict 데이터인데 validate_chart_data 에
# 분기가 없어 *항상* list[dict] else 로 떨어져 100% silent drop 되던 회귀 (v8.0.0~v8.2.9).
# 르포 관계도가 한 번도 안 떴던 근본 원인. 유효 데이터는 반드시 통과해야 한다.
def test_stakeholder_map_valid_dict_passes() -> None:
    ok, reason = validate_chart_data(
        "stakeholder_map",
        {
            "nodes": [
                {"id": "samsung", "label": "삼성전자", "col": "left", "flag": "KR"},
                {"id": "nvidia", "label": "엔비디아", "col": "right", "flag": "US"},
            ],
            "edges": [{"source": "samsung", "target": "nvidia", "type": "공급"}],
        },
    )
    assert ok, f"유효 stakeholder_map 이 drop 됨 (CHART-AP-38 회귀): {reason}"


def test_stakeholder_map_rejects_dangling_edge() -> None:
    ok, reason = validate_chart_data(
        "stakeholder_map",
        {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
         "edges": [{"source": "a", "target": "ZZZ"}]},
    )
    assert not ok and "nodes 에 없음" in reason


def test_stakeholder_map_rejects_non_dict() -> None:
    ok, reason = validate_chart_data("stakeholder_map", [{"id": "a"}])
    assert not ok and "dict 형식 필요" in reason


def test_every_dict_guard_type_has_dispatch_branch() -> None:
    """CHART-AP-38 일반화 — _TYPE_TO_GUARD 에 등록됐는데 dict 데이터를 받는 가드가
    validate_chart_data 에서 list else 로 떨어지지 않는지(= 100% drop 회귀 차단)."""
    from src.visual.schemas import _TYPE_TO_GUARD
    # 대표 dict 형식 type 들 — 유효 최소 데이터로 통과해야 한다.
    samples = {
        "stakeholder_map": {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                            "edges": [{"source": "a", "target": "b"}]},
        "sankey": {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                   "links": [{"source": "a", "target": "b", "value": 1}]},
        # v8.6.2 — 위계 2종도 dict 계약 (elif 분기 누락 시 100% silent drop)
        "treemap": {"children": [
            {"label": "A", "children": [{"label": "a1", "value": 3}, {"label": "a2", "value": 2}]},
            {"label": "B", "children": [{"label": "b1", "value": 4}]},
        ]},
        "tree": {"root": {"label": "root", "children": [
            {"label": "A", "children": [{"label": "a1"}]},
            {"label": "B"},
        ]}},
    }
    for ctype, data in samples.items():
        assert ctype in _TYPE_TO_GUARD, f"{ctype} 가드 미등록"
        ok, reason = validate_chart_data(ctype, data)
        assert ok, f"{ctype} 유효 dict 데이터가 drop 됨: {reason}"


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


# CHART-AP-44 — StackedBar: 계약은 {scenarios:[{name, segments}]} (프롬프트·렌더러·템플릿 정합)
def test_stacked_guard_accepts_prompt_shape() -> None:
    """composer SYSTEM_PROMPT 가 문서화한 scenarios 형태가 통과해야 한다.

    구 가드는 {categories, series} 를 요구해 프롬프트 준수 stacked 가
    100% silent drop 됐다 (CHART-AP-44, CHART-AP-38 동일 클래스).
    """
    StackedBarGuard(scenarios=[
        {"name": "낙관", "segments": [{"label": "수출", "value": 40}, {"label": "내수", "value": 30}]},
        {"name": "비관", "segments": [{"label": "수출", "value": 22}, {"label": "내수", "value": 18}]},
    ])


def test_stacked_guard_rejects_legacy_categories_series() -> None:
    """구 {categories, series} 형태는 렌더 불가(템플릿 has_data 탈락) — reject."""
    with pytest.raises(Exception):
        StackedBarGuard(
            categories=["a", "b"],
            series=[{"name": "x", "values": [1, 2]}],
        )


def test_stacked_guard_rejects_nan_value() -> None:
    with pytest.raises(Exception):
        StackedBarGuard(scenarios=[
            {"name": "x", "segments": [{"label": "a", "value": float("nan")}]},
        ])


def test_stacked_guard_rejects_negative_value() -> None:
    """value 는 양수 magnitude (프롬프트 계약 — 부호 있는 점수는 bar)."""
    with pytest.raises(Exception):
        StackedBarGuard(scenarios=[
            {"name": "x", "segments": [{"label": "a", "value": -3}]},
        ])


# CHART-AP-44 — Heatmap 양형 수용
def test_heatmap_guard_accepts_severity_rows() -> None:
    """v7.1.0 강도 트랙 계약 [{title, severity}] — 프롬프트·렌더러가 쓰는 형태."""
    HeatmapGuard(data=[
        {"title": "공급 차질", "severity": "high"},
        {"title": "수요 둔화", "severity": "low"},
    ])


def test_heatmap_guard_accepts_grid_cells() -> None:
    """격자형 [{x, y, value}] — 결정 트리 §6 의 2축 조합 강도."""
    HeatmapGuard(data=[
        {"x": "대만", "y": "파운드리", "value": 5},
        {"x": "한국", "y": "메모리", "value": 3},
    ])


def test_heatmap_guard_rejects_unknown_severity() -> None:
    with pytest.raises(Exception):
        HeatmapGuard(data=[{"title": "x", "severity": "extreme"}])


def test_heatmap_guard_rejects_grid_nan() -> None:
    with pytest.raises(Exception):
        HeatmapGuard(data=[{"x": "a", "y": "b", "value": float("nan")}])


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
    통과는 별개.

    v8.6.2 — 예시 type 을 treemap → chord 로 교체. treemap 은 렌더러가 실장되면서
    experimental → guarded 로 승격돼 더는 이 케이스의 대표가 아니다 (플랜 §5.1).
    """
    chart = {
        "type": "chord",
        "title": "테스트",
        "data": [
            {"source": "X", "target": "Y", "value": 30},
            {"source": "Y", "target": "Z", "value": 50},
        ],
        "source_ids": ["S-001"],
    }
    prose = "X→Y 30, Y→Z 50 — chord 로 표현."
    result = run_chart_gate(
        chart, section_prose=prose, must_have_types=["chord"]
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

# ─────────────────────────────────────────────────────────────
# v7.5.0 — 이중 축 결합 + 사회 이슈 어휘 4종 (combo / diverging_bar /
# pyramid / dot_matrix) 가드
# ─────────────────────────────────────────────────────────────

_COMBO_OK = {
    "bars": {"label": "거래대금", "unit": "조원", "series": [
        {"x": "03", "y": 12.1}, {"x": "04", "y": 15.4}, {"x": "05", "y": 11.0},
        {"x": "06", "y": 18.9},
    ]},
    "line": {"label": "코스피", "unit": "pt", "series": [
        {"x": "03", "y": 2701}, {"x": "04", "y": 2748}, {"x": "05", "y": 2810},
        {"x": "06", "y": 2948},
    ]},
}


def test_combo_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("combo", _COMBO_OK)
    assert ok, reason


def test_combo_guard_rejects_too_few_bars() -> None:
    bad = {
        "bars": {"label": "b", "series": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]},
        "line": {"label": "l", "series": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]},
    }
    ok, _ = validate_chart_data("combo", bad)
    assert not ok  # bars <3 — bar 로 대체해야


def test_combo_guard_rejects_list_payload() -> None:
    ok, reason = validate_chart_data("combo", [{"x": 1, "bar": 2, "line": 3}])
    assert not ok
    assert "dict" in reason


def test_diverging_bar_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("diverging_bar", [
        {"label": "20대", "neg": 41.0, "pos": 35.0},
        {"label": "30대", "neg": 38.0, "pos": 40.0},
        {"label": "60대 이상", "neg": 22.0, "pos": 61.0},
    ])
    assert ok, reason


def test_diverging_bar_guard_rejects_negative_and_single_row() -> None:
    ok, _ = validate_chart_data("diverging_bar", [
        {"label": "a", "neg": -5.0, "pos": 10.0},
        {"label": "b", "neg": 3.0, "pos": 4.0},
    ])
    assert not ok  # neg/pos 는 양수 magnitude — 좌우 방향이 부호
    ok, _ = validate_chart_data("diverging_bar", [{"label": "a", "neg": 1.0, "pos": 2.0}])
    assert not ok  # 1행 — 대립 쌍 비교가 아님


def test_diverging_bar_guard_rejects_all_zero_row() -> None:
    ok, _ = validate_chart_data("diverging_bar", [
        {"label": "a", "neg": 0, "pos": 0},
        {"label": "b", "neg": 3.0, "pos": 4.0},
    ])
    assert not ok


def test_pyramid_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("pyramid", [
        {"bracket": "0-9", "left": 180.0, "right": 171.0},
        {"bracket": "10-19", "left": 232.0, "right": 219.0},
        {"bracket": "20-29", "left": 340.0, "right": 308.0},
        {"bracket": "30-39", "left": 351.0, "right": 330.0},
        {"bracket": "40-49", "left": 405.0, "right": 392.0},
    ])
    assert ok, reason


def test_pyramid_guard_rejects_too_few_brackets_and_nan() -> None:
    rows = [{"bracket": f"b{i}", "left": 1.0, "right": 2.0} for i in range(3)]
    ok, _ = validate_chart_data("pyramid", rows)
    assert not ok  # <4행 — 피라미드 형태가 아님
    rows = [{"bracket": f"b{i}", "left": 1.0, "right": 2.0} for i in range(4)]
    rows[0]["left"] = float("nan")
    ok, _ = validate_chart_data("pyramid", rows)
    assert not ok


def test_dot_matrix_guard_accepts_realistic() -> None:
    ok, reason = validate_chart_data("dot_matrix", [
        {"label": "비정규직", "value": 37.0, "accent": True},
        {"label": "정규직", "value": 63.0},
    ])
    assert ok, reason


def test_dot_matrix_guard_rejects_nonpositive_and_too_many() -> None:
    ok, _ = validate_chart_data("dot_matrix", [
        {"label": "a", "value": 0}, {"label": "b", "value": 10.0},
    ])
    assert not ok  # value 는 양수만
    segs = [{"label": f"s{i}", "value": 10.0} for i in range(7)]
    ok, _ = validate_chart_data("dot_matrix", segs)
    assert not ok  # 2~6 segment 한정


def test_dot_matrix_guard_rejects_single_segment() -> None:
    ok, _ = validate_chart_data("dot_matrix", [{"label": "전체", "value": 100.0}])
    assert not ok


# ─── v8.6.1 — 표현 전환 옵션 가드 (CHART_REDESIGN_V8_6_PLAN §4) ─────────

def test_bar_guard_accepts_prior_and_rejects_nonfinite_prior() -> None:
    """§4.1 — 행 단위 `prior` 는 선택 필드, 값은 유한해야 한다."""
    ok, reason = validate_chart_data("bar", [
        {"label": "무료", "value": 38, "prior": 31},
        {"label": "프로", "value": 22, "prior": 16},
    ])
    assert ok, reason
    ok, _ = validate_chart_data("bar", [{"label": "무료", "value": 38, "prior": float("inf")}])
    assert not ok


def test_range_bar_guard_accepts_before_after_rows() -> None:
    """§4.6 — before_after 는 *양방향* 이 정상 (개편 후 값이 줄어드는 것도 결과)."""
    ok, reason = validate_chart_data("range_bar", [
        {"label": "초대 흐름", "before": 14, "after": 6},
        {"label": "첫 보드", "before": 19, "after": 9},
        {"label": "정산", "before": 17, "after": 21},
    ])
    assert ok, reason


def test_range_bar_guard_rejects_flat_before_after_and_mixed_forms() -> None:
    ok, _ = validate_chart_data("range_bar", [
        {"label": "a", "before": 10, "after": 10},
        {"label": "b", "before": 19, "after": 9},
        {"label": "c", "before": 17, "after": 21},
    ])
    assert not ok  # before == after → 덤벨이 점으로 붕괴
    ok, _ = validate_chart_data("range_bar", [
        {"label": "a", "low": 1, "high": 2},
        {"label": "b", "before": 19, "after": 9},
        {"label": "c", "low": 3, "high": 9},
    ])
    assert not ok  # 한 차트에 두 행 형식 혼용 금지


def test_range_bar_guard_still_rejects_low_ge_high() -> None:
    """기존 계약 보존 — low >= high 는 여전히 drop."""
    ok, _ = validate_chart_data("range_bar", [
        {"label": "a", "low": 20, "high": 10},
        {"label": "b", "low": 1, "high": 2},
        {"label": "c", "low": 3, "high": 9},
    ])
    assert not ok


def test_option_guard_rejects_out_of_contract_texture() -> None:
    """§4.1 — texture / orientation / unit 은 Literal·양수 계약."""
    from src.visual.schemas import validate_chart_options
    assert validate_chart_options("bar", {"texture": "capsule"})[0]
    assert not validate_chart_options("bar", {"texture": "wave"})[0]
    assert not validate_chart_options("bar", {"orientation": "sideways"})[0]
    assert not validate_chart_options("bar", {"unit": 0})[0]


def test_option_guard_passes_legacy_payloads_untouched() -> None:
    """v8.6.0 이전 payload(옵션 없음)는 어떤 type 이든 통과 — 소급 안전."""
    from src.visual.schemas import validate_chart_options
    for ctype in ("bar", "line", "area", "scatter", "range_bar", "heatmap", "lollipop"):
        assert validate_chart_options(ctype, {"type": ctype, "data": []})[0], ctype


# ─── v8.6.2 — 위계 2종 (CHART_REDESIGN_V8_6_PLAN §5.1 / §5.2) ───────────

_TREEMAP_OK = {
    "children": [
        {"label": "메모리", "children": [
            {"label": "DRAM", "value": 320}, {"label": "NAND", "value": 190},
            {"label": "HBM", "value": 140},
        ]},
        {"label": "시스템", "children": [
            {"label": "파운드리", "value": 210}, {"label": "설계", "value": 95},
        ]},
    ],
    "unit_label": "억 달러",
}

_TREE_OK = {
    "root": {"label": "○○지주", "children": [
        {"label": "금융", "children": [
            {"label": "○○은행", "note": "지분 100%"}, {"label": "○○증권"},
        ]},
        {"label": "산업", "children": [{"label": "○○중공업"}]},
    ]},
}


def test_treemap_guard_accepts_two_level_composition() -> None:
    ok, reason = validate_chart_data("treemap", _TREEMAP_OK)
    assert ok, reason


def test_treemap_guard_rejects_flat_and_deep_and_nonpositive() -> None:
    flat = {"children": [{"label": "A", "value": 3}, {"label": "B", "value": 5}]}
    assert not validate_chart_data("treemap", flat)[0]      # 1층은 bar/donut 자리
    deep = {"children": [
        {"label": "A", "children": [{"label": "a", "children": [{"label": "x", "value": 1}]}]},
        {"label": "B", "children": [{"label": "b", "value": 2}]},
    ]}
    assert not validate_chart_data("treemap", deep)[0]      # 깊이 3층
    zero = {"children": [
        {"label": "A", "children": [{"label": "a", "value": 0}, {"label": "a2", "value": 1}]},
        {"label": "B", "children": [{"label": "b", "value": 2}]},
    ]}
    assert not validate_chart_data("treemap", zero)[0]      # 잎 value 는 양수


def test_treemap_guard_rejects_parent_child_sum_mismatch() -> None:
    """부모 value 를 적었으면 자식 합과 맞아야 한다 — 어긋나면 어느 쪽이 참인지 모른다."""
    bad = {"children": [
        {"label": "A", "value": 900, "children": [{"label": "a", "value": 100}]},
        {"label": "B", "children": [{"label": "b", "value": 50}, {"label": "b2", "value": 20}]},
    ]}
    assert not validate_chart_data("treemap", bad)[0]
    good = {"children": [
        {"label": "A", "value": 100, "children": [{"label": "a", "value": 100}]},
        {"label": "B", "children": [{"label": "b", "value": 50}, {"label": "b2", "value": 20}]},
    ]}
    assert validate_chart_data("treemap", good)[0]


def test_treemap_guard_rejects_list_form() -> None:
    """CHART-AP-38 — dict 계약인데 list 로 오면 명시적으로 거절 (침묵 금지)."""
    ok, reason = validate_chart_data("treemap", [{"label": "A", "value": 1}])
    assert not ok and "dict" in reason


def test_tree_guard_accepts_ownership_hierarchy() -> None:
    ok, reason = validate_chart_data("tree", _TREE_OK)
    assert ok, reason


def test_tree_guard_rejects_shallow_deep_and_wide() -> None:
    assert not validate_chart_data("tree", {"root": {"label": "혼자"}})[0]   # 노드 4 미만
    deep = {"root": {"label": "r", "children": [
        {"label": "a", "children": [
            {"label": "b", "children": [{"label": "c", "children": [{"label": "d"}]}]},
        ]},
        {"label": "e"},
    ]}}
    assert not validate_chart_data("tree", deep)[0]                          # 깊이 4층
    wide = {"root": {"label": "r", "children": [
        {"label": "g", "children": [{"label": f"n{i}"} for i in range(9)]},
    ]}}
    assert not validate_chart_data("tree", wide)[0]                          # 자식 9개


def test_tree_guard_rejects_overlong_label_and_note() -> None:
    long_label = {"root": {"label": "r", "children": [
        {"label": "가" * 19}, {"label": "b"}, {"label": "c"},
    ]}}
    assert not validate_chart_data("tree", long_label)[0]
    long_note = {"root": {"label": "r", "children": [
        {"label": "a", "note": "나" * 25}, {"label": "b"}, {"label": "c"},
    ]}}
    assert not validate_chart_data("tree", long_note)[0]


def test_hierarchy_types_pass_template_gate() -> None:
    """CHART-AP-45 — 가드를 통과해도 템플릿 has_data 게이트에서 사라지면 안 된다."""
    from src.visual.schemas import chart_renderable
    assert chart_renderable({"type": "treemap", "data": _TREEMAP_OK})
    assert chart_renderable({"type": "tree", "data": _TREE_OK})
    # 묶음이 하나뿐이면 treemap 이 아니다 (_MIN_LEN_REQUIREMENTS)
    assert not chart_renderable({"type": "treemap", "data": {
        "children": [{"label": "A", "children": [{"label": "a", "value": 1}]}]}})
