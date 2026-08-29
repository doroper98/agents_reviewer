"""v5.2.0 — ComposedSection._drop_invalid_charts 회귀 테스트.

chart_gate 의 production 진입점. composer LLM 출력의 차트 dict 들이
src/visual/schemas.py 의 type 별 가드를 *실제로* 통과/탈락하는지 검증.
이 validator 가 디폴트 ON 이므로 운영 영향 큼.

검증 원칙:
- 합법 차트는 절대 안 건드림
- 위반 차트만 drop (warning log)
- 보고서 자체는 절대 reject 안 됨 (composer 토큰 비용 보호)
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.models import ComposedSection


def _section(charts: list[dict]) -> ComposedSection:
    return ComposedSection(
        heading="테스트 섹션",
        prose="본문 내용",
        charts=charts,
    )


# ─── 합법 차트는 보존 ─────────────────────────────────────────────


def test_keeps_valid_bar_chart() -> None:
    s = _section([
        {"type": "bar", "title": "OK", "data": [
            {"label": "A", "value": 10},
            {"label": "B", "value": 20},
        ]},
    ])
    assert len(s.charts) == 1
    assert s.charts[0]["title"] == "OK"


def test_keeps_valid_line_chart() -> None:
    s = _section([
        {"type": "line", "title": "추이", "data": [
            {"x": "2026-05-13", "y": 7900},
            {"x": "2026-05-15", "y": 8002.66},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_valid_candle() -> None:
    s = _section([
        {"type": "candle", "title": "삼성전자", "data": [
            {"date": "2026-05-13", "open": 92000, "high": 93500, "low": 91500, "close": 93000},
            {"date": "2026-05-14", "open": 93000, "high": 94200, "low": 92800, "close": 94000},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_valid_donut_3_segments() -> None:
    s = _section([
        {"type": "donut", "title": "구성", "data": [
            {"label": "반도체", "value": 16.8},
            {"label": "금융", "value": 1.2},
            {"label": "기타", "value": 2.2},
        ]},
    ])
    assert len(s.charts) == 1


# ─── 위반 차트는 drop ─────────────────────────────────────────────


def test_drops_2_segment_donut() -> None:
    """CHART-AP-16 의 실제 회귀 케이스 — composer 가 다시 emit 해도 자동 drop."""
    s = _section([
        {"type": "donut", "title": "구성", "data": [
            {"label": "반도체", "value": 16.8},
            {"label": "비반도체", "value": 3.4},
        ]},
    ])
    assert s.charts == []


def test_drops_zero_duration_gantt() -> None:
    """CHART-AP-15 — 모든 row 가 zero-duration 인 gantt."""
    s = _section([
        {"type": "gantt", "title": "타임라인", "data": [
            {"label": "A", "start": "2026-05-11", "end": "2026-05-11"},
            {"label": "B", "start": "2026-05-12", "end": "2026-05-12"},
            {"label": "C", "start": "2026-05-15", "end": "2026-05-15"},
        ]},
    ])
    assert s.charts == []


def test_drops_inverted_ohlc_candle() -> None:
    """OHLC 순서 위반 — low > high 등."""
    s = _section([
        {"type": "candle", "title": "삼전", "data": [
            {"date": "2026-05-14", "open": 100, "high": 110, "low": 95, "close": 105},
            {"date": "2026-05-15", "open": 100, "high": 90, "low": 95, "close": 105},
        ]},
    ])
    assert s.charts == []


def test_drops_negative_bar_value_passes() -> None:
    """음수 bar 는 BarChartGuard 가 finite 만 보고 음수 통과 — 보존됨."""
    s = _section([
        {"type": "bar", "title": "순매도", "data": [
            {"label": "A", "value": -100},
            {"label": "B", "value": 50},
        ]},
    ])
    assert len(s.charts) == 1


# ─── 혼합 — 합법 + 위반 mix ────────────────────────────────────────


def test_drops_only_invalid_keeps_rest() -> None:
    """3개 차트 중 1개만 invalid → 2개 보존."""
    s = _section([
        {"type": "bar", "title": "OK1", "data": [
            {"label": "A", "value": 10},
        ]},
        {"type": "donut", "title": "BAD", "data": [  # AP-16
            {"label": "X", "value": 50},
            {"label": "Y", "value": 50},
        ]},
        {"type": "line", "title": "OK2", "data": [
            {"x": "2026-05-13", "y": 100},
            {"x": "2026-05-15", "y": 110},
        ]},
    ])
    assert len(s.charts) == 2
    titles = [c["title"] for c in s.charts]
    assert "OK1" in titles and "OK2" in titles
    assert "BAD" not in titles


# ─── Edge cases — section 생성 자체는 절대 fail 하면 안 됨 ──────────


def test_empty_charts_passes() -> None:
    s = ComposedSection(heading="제목", prose="본문", charts=[])
    assert s.charts == []


def test_missing_type_preserves_chart() -> None:
    """type 누락 dict 는 downstream 호환 위해 보존."""
    s = _section([
        {"title": "type 없음", "data": [{"label": "A", "value": 1}]},
    ])
    assert len(s.charts) == 1


def test_non_dict_in_charts_rejected_by_field_validation() -> None:
    """charts: list[dict] — Pydantic field 가 비-dict 를 reject. 정상 동작 (composer LLM 은 dict 만 emit)."""
    with pytest.raises(Exception):
        ComposedSection(
            heading="제목", prose="본문",
            charts=["잘못된 항목"],  # type: ignore[list-item]
        )


def test_unknown_type_preserved() -> None:
    """guard_for_type 이 None 반환 → validate_chart_data 가 ok=True 반환 → 보존."""
    s = _section([
        {"type": "treemap", "title": "신규 type", "data": [
            {"name": "A", "value": 1},
        ]},
    ])
    assert len(s.charts) == 1


def test_validator_runs_only_once_not_on_each_attr_access() -> None:
    """model_validator(mode='after') 는 생성 시 1회만 — 이후 self.charts 접근에 영향 X."""
    s = _section([
        {"type": "donut", "title": "BAD", "data": [
            {"label": "X", "value": 50},
            {"label": "Y", "value": 50},
        ]},
    ])
    # 처음 접근 시 이미 drop 됨
    assert s.charts == []
    # 다시 접근해도 동일
    assert s.charts == []


# ─── _select_market_period (mode-aware) ───────────────────────────


def test_market_period_default_3m() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="코스피 8000 돌파")
    ctx = ContextAnalysis(event_name="코스피 8000 돌파", summary="사상 첫 돌파")
    assert _select_market_period(req, ctx) == "3M"


def test_market_period_daily_briefing() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="간밤 미국 증시 마감 분석")
    ctx = ContextAnalysis(event_name="간밤 산업 동향", summary="어제 발표")
    assert _select_market_period(req, ctx) == "1M"


def test_market_period_historical() -> None:
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="IMF 외환위기 이후 처음")
    ctx = ContextAnalysis(event_name="역사적 회고", summary="10년 만에")
    assert _select_market_period(req, ctx) == "3Y"


def test_market_period_historical_keyword_priority() -> None:
    """historical 키워드가 daily 보다 우선 (먼저 매치)."""
    from src.orchestrator import _select_market_period
    from src.models import AnalysisRequest, ContextAnalysis
    req = AnalysisRequest(event_description="간밤 IMF 비교")
    ctx = ContextAnalysis()
    assert _select_market_period(req, ctx) == "3Y"


# ─── _ensure_time_series_chart (v5.2.0+ 결정적 안전망) ──────────────


def _composed_with_charts(charts: list[dict]) -> "ComposedReport":
    from src.models import ComposedReport, ComposedSection
    return ComposedReport(
        headline="제목",
        sections=[
            ComposedSection(heading="섹션 1", prose="본문", charts=charts),
            ComposedSection(heading="섹션 2", prose="본문"),
        ],
    )


def _make_context(time_series=None, timeline=None, summary="") -> "ContextAnalysis":
    from src.models import ContextAnalysis
    return ContextAnalysis(
        event_name="테스트 사건",
        summary=summary,
        timeline=timeline or [],
        time_series=time_series or [],
    )


def _candle_ts(instrument: str = "삼성전자") -> dict:
    return {
        "instrument": instrument,
        "source": "KRX",
        "code": "005930",
        "chart_type": "candle",
        "unit": "원",
        "start_date": "2026-04-15",
        "end_date": "2026-05-15",
        "data": [
            {"date": "2026-05-13", "open": 264000, "high": 285500, "low": 263000, "close": 284000},
            {"date": "2026-05-14", "open": 282000, "high": 299500, "low": 281500, "close": 296000},
            {"date": "2026-05-15", "open": 291000, "high": 296500, "low": 268500, "close": 270500},
        ],
    }


def _line_ts(instrument: str = "코스피") -> dict:
    return {
        "instrument": instrument,
        "source": "YAHOO",
        "code": "^KS11",
        "chart_type": "line",
        "start_date": "2026-04-15",
        "end_date": "2026-05-15",
        "data": [
            {"date": "2026-05-13", "open": 7400, "high": 7500, "low": 7380, "close": 7480},
            {"date": "2026-05-14", "open": 7480, "high": 7600, "low": 7460, "close": 7580},
            {"date": "2026-05-15", "open": 7580, "high": 8002, "low": 7480, "close": 7493},
        ],
    }


def test_ensure_ts_chart_adds_when_composer_skipped() -> None:
    """case C 회귀 — composer 가 시계열 차트 0개 + time_series 있음.
    v5.2.2: 적극 모드 — 후보 series *전부* 추가."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([
        {"type": "bar", "title": "투자자 매매", "data": [{"label": "외인", "value": -1}]},
        {"type": "donut", "title": "점유율", "data": [
            {"label": "A", "value": 1}, {"label": "B", "value": 1}, {"label": "C", "value": 1},
        ]},
    ])
    ctx = _make_context(time_series=[_candle_ts(), _line_ts()])
    _ensure_time_series_chart(composed, ctx)
    # 기존 2개 + 신규 2개 (candle + line 모두 추가)
    sec0_charts = composed.sections[0].charts
    assert len(sec0_charts) == 4
    # 새로 박힌 두 개는 시계열 type
    assert {sec0_charts[0]["type"], sec0_charts[1]["type"]} <= {"line", "candle", "area"}


def test_ensure_ts_chart_noop_when_composer_already_emitted_for_instrument() -> None:
    """composer 가 같은 instrument 시계열 차트 박았으면 *그 instrument 는* skip.
    v5.2.2: 단 다른 instrument 는 보충."""
    from src.orchestrator import _ensure_time_series_chart
    pre = [
        {"type": "candle", "title": "삼성전자 (005930)", "data": [
            {"date": "2026-05-14", "open": 282000, "high": 299500, "low": 281500, "close": 296000},
            {"date": "2026-05-15", "open": 291000, "high": 296500, "low": 268500, "close": 270500},
        ]},
    ]
    composed = _composed_with_charts(pre)
    ctx = _make_context(time_series=[_candle_ts(), _line_ts()])  # 삼성 + 코스피
    _ensure_time_series_chart(composed, ctx)
    # 삼성전자 는 composer 박음 → skip / 코스피 는 hook 이 추가 (1개 보충)
    assert len(composed.sections[0].charts) == 2  # 기존 1 + 코스피 1
    titles = [c.get("title", "") for c in composed.sections[0].charts]
    assert any("코스피" in t for t in titles)


def test_ensure_ts_chart_noop_when_composer_all_instruments() -> None:
    """composer 가 *모든* mention 된 instrument 시계열 차트 박으면 hook 노op."""
    from src.orchestrator import _ensure_time_series_chart
    pre = [
        {"type": "candle", "title": "삼성전자 (005930)", "data": [
            {"date": "2026-05-15", "open": 291000, "high": 296500, "low": 268500, "close": 270500},
        ]},
        {"type": "line", "title": "코스피 종합지수", "data": [
            {"x": "2026-05-15", "y": 7493},
        ]},
    ]
    composed = _composed_with_charts(pre)
    ctx = _make_context(time_series=[_candle_ts(), _line_ts()])
    _ensure_time_series_chart(composed, ctx)
    # 변경 없음
    assert len(composed.sections[0].charts) == 2


def test_ensure_ts_chart_noop_when_no_time_series() -> None:
    """time_series 비어있으면 hook 노op."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([
        {"type": "bar", "title": "투자자 매매", "data": [{"label": "외인", "value": -1}]},
    ])
    _ensure_time_series_chart(composed, _make_context())
    assert len(composed.sections[0].charts) == 1


def test_ensure_ts_chart_noop_when_time_series_data_empty() -> None:
    """time_series 항목은 있지만 data 모두 비어있으면 hook 노op."""
    from src.orchestrator import _ensure_time_series_chart
    empty_ts = [{"instrument": "X", "source": "?", "data": []}]
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=empty_ts))
    assert composed.sections[0].charts == []


def test_ensure_ts_chart_noop_when_no_sections() -> None:
    """sections 없으면 hook 노op (방어)."""
    from src.orchestrator import _ensure_time_series_chart
    from src.models import ComposedReport
    composed = ComposedReport(headline="제목", sections=[])
    _ensure_time_series_chart(composed, _make_context(time_series=[_candle_ts()]))
    assert composed.sections == []


def test_ensure_ts_chart_respects_chart_type_for_candle() -> None:
    """series.chart_type=candle 이면 OHLC shape 그대로 유지."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_candle_ts()]))
    ch = composed.sections[0].charts[0]
    assert ch["type"] == "candle"
    row0 = ch["data"][0]
    assert "open" in row0 and "high" in row0 and "low" in row0 and "close" in row0


def test_ensure_ts_chart_maps_xy_for_line() -> None:
    """series.chart_type=line 이면 {x, y} 형태로 변환."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_line_ts()]))
    ch = composed.sections[0].charts[0]
    assert ch["type"] == "line"
    row0 = ch["data"][0]
    assert "x" in row0 and "y" in row0
    assert row0["x"] == "2026-05-13"
    assert row0["y"] == 7480
    assert "open" not in row0


def test_ensure_ts_chart_priority_data_rich_series_first() -> None:
    """후보 여러 개면 data 가장 많은 series 가 sections[0].charts[0]."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    short = _candle_ts("적은데이터")
    short["data"] = short["data"][:1]  # 1 bar
    long_ = _line_ts("많은데이터")  # 3 bars
    _ensure_time_series_chart(composed, _make_context(time_series=[short, long_]))
    # 첫번째 차트가 data 많은 쪽
    assert "많은데이터" in composed.sections[0].charts[0]["title"]


# ─── v5.2.2 — mockup 품질 검증 ──────────────────────────────────


def test_ts_chart_title_korean_for_index() -> None:
    """Yahoo 지수 → '코스피 종합지수' 형태."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_line_ts("코스피")]))
    assert composed.sections[0].charts[0]["title"] == "코스피 종합지수"


def test_ts_chart_title_korean_for_stock_with_code() -> None:
    """KRX 개별주 → '삼성전자 (005930)' 형태."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_candle_ts()]))
    assert composed.sections[0].charts[0]["title"] == "삼성전자 (005930)"


def test_ts_chart_subtitle_includes_pct_change() -> None:
    """Subtitle 에 변화율 % + 기간 표시."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_candle_ts()]))
    sub = composed.sections[0].charts[0]["subtitle"]
    assert "2026-04-15" in sub and "2026-05-15" in sub
    # 284,000 → 270,500 = -4.75% 정도
    assert "-" in sub and "%" in sub
    assert "284,000" in sub or "284" in sub


def test_ts_chart_source_display_korean() -> None:
    """source 가 사용자 노출 형태 — 'Yahoo Finance / ... · 일간'."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_line_ts()]))
    src = composed.sections[0].charts[0]["source"]
    assert "Yahoo Finance" in src
    assert "일간" in src


def test_ts_chart_takeaway_from_summary() -> None:
    """본문 summary 첫 문장이 takeaway 로 활용."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    ctx = _make_context(
        time_series=[_line_ts()],
        summary="코스피가 사상 처음 8000선을 돌파한 직후 6% 폭락. 외국인 8조 순매도. 이후 분석.",
    )
    _ensure_time_series_chart(composed, ctx)
    take = composed.sections[0].charts[0]["takeaway"]
    assert "코스피" in take and "8000" in take


def test_ts_chart_takeaway_fallback_to_volatility() -> None:
    """summary 없으면 변동성 기반 자동 해석."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_line_ts()]))
    take = composed.sections[0].charts[0]["takeaway"]
    # 변동폭 표현 포함
    assert "변동폭" in take or "%" in take


def test_ts_chart_event_markers_from_timeline() -> None:
    """context.timeline 의 date 와 매치되는 row 에 event 필드 자동 부착.

    charts.js 는 event 필드 보고 번호 배지 + footnote 자동 렌더 — mockup 핵심.
    """
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    ctx = _make_context(
        time_series=[_line_ts()],
        timeline=[
            {"date": "2026-05-13", "event": "외국인 14.5조 순매도 돌파"},
            {"date": "2026-05-15", "event": "코스피 8000 첫 돌파"},
        ],
    )
    _ensure_time_series_chart(composed, ctx)
    data = composed.sections[0].charts[0]["data"]
    # 5/13 row 와 5/15 row 에 event 부착
    by_date = {d["x"]: d for d in data}
    assert "event" in by_date["2026-05-13"]
    assert "14.5조" in by_date["2026-05-13"]["event"]
    assert "event" in by_date["2026-05-15"]
    assert "8000" in by_date["2026-05-15"]["event"]
    # 5/14 row 는 매치 timeline 없으니 event 부착 X
    assert "event" not in by_date["2026-05-14"]


def test_ts_chart_event_markers_candle() -> None:
    """candle 차트도 동일 — timeline 매칭으로 event 필드 부착."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    ctx = _make_context(
        time_series=[_candle_ts()],
        timeline=[
            {"date": "2026-05-15", "event": "삼전 -8.6% 단일 폭락"},
        ],
    )
    _ensure_time_series_chart(composed, ctx)
    data = composed.sections[0].charts[0]["data"]
    by_date = {d["date"]: d for d in data}
    assert "event" in by_date["2026-05-15"]
    assert "8.6%" in by_date["2026-05-15"]["event"]


def test_ts_chart_no_event_markers_when_timeline_empty() -> None:
    """timeline 없으면 event 부착 X (회귀 가드)."""
    from src.orchestrator import _ensure_time_series_chart
    composed = _composed_with_charts([])
    _ensure_time_series_chart(composed, _make_context(time_series=[_line_ts()]))
    data = composed.sections[0].charts[0]["data"]
    assert all("event" not in d for d in data)


# ─── CHART-AP-44 — 프롬프트 준수 heatmap/stacked 는 보존 (v8.5.11) ─────────
# 프롬프트↔가드 계약 불일치로 두 type 이 100% silent drop 되던 회귀의 재발 방지.
# (heatmap: v7.1.0 강도 트랙 계약 + 신규 격자형 / stacked: scenarios 계약)


def test_keeps_prompt_shape_heatmap_severity() -> None:
    s = _section([
        {"type": "heatmap", "title": "위험도", "data": [
            {"title": "공급 차질", "severity": "high"},
            {"title": "수요 둔화", "severity": "medium"},
            {"title": "재고 소진", "severity": "low"},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_prompt_shape_heatmap_grid() -> None:
    s = _section([
        {"type": "heatmap", "title": "국가×항목", "data": [
            {"x": "대만", "y": "파운드리", "value": 5},
            {"x": "대만", "y": "패키징", "value": 4},
            {"x": "한국", "y": "파운드리", "value": 3},
            {"x": "한국", "y": "패키징", "value": 3},
        ]},
    ])
    assert len(s.charts) == 1


def test_keeps_prompt_shape_stacked_scenarios() -> None:
    s = _section([
        {"type": "stacked", "title": "시나리오", "data": {"scenarios": [
            {"name": "낙관", "segments": [{"label": "수출", "value": 40}, {"label": "내수", "value": 30}]},
            {"name": "비관", "segments": [{"label": "수출", "value": 22}, {"label": "내수", "value": 18}]},
        ]}},
    ])
    assert len(s.charts) == 1


def test_drops_stacked_legacy_categories_series() -> None:
    """구 {categories, series} 는 렌더 불가 형태 — drop 유지."""
    s = _section([
        {"type": "stacked", "title": "legacy", "data": {
            "categories": ["a", "b"],
            "series": [{"name": "x", "values": [1, 2]}],
        }},
    ])
    assert len(s.charts) == 0
