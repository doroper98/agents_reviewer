"""v7.0.2 — CHART-AP-31: composer 시계열 차트의 일별 밀도 보장 회귀.

composer LLM 이 차트 데이터를 손으로 emit 하면서 일별 series (3M ≈ 60거래일) 를
토큰 절약으로 듬성하게 추려 쓰는 회귀 (사용자 catch — "지수 차트는 일별 종가가
기준이어야, 저렇게는 너무 정보가 없다"). `_densify_ts_charts` 가 0-LLM 으로
실측 행 교체를 보장하는지 검증.

가드 대상:
  1. 듬성한 line 차트 → 차트 자신의 날짜 창 안 전체 일별 행으로 교체
  2. composer 의 의도적 확대 창 (사건 주간) 은 보존 — 창 *안* 만 densify
  3. 단축 날짜 표기 ("06-04") → 창 해석 불가 → 전체 series 교체 (원칙 우선)
  4. 이벤트 마커 (row.event) 날짜/suffix 매칭 보존
  5. candle 은 OHLC 행 그대로 교체
  6. 이미 일별 밀도 / compact strip / 비매칭 title 은 불변
"""

from __future__ import annotations

from src.models import ComposedReport, ComposedSection, ContextAnalysis
from src.orchestrator import _densify_ts_charts


def _daily_series(n: int = 60, name: str = "코스피") -> dict:
    data = []
    for i in range(n):
        m, d = divmod(i, 30)
        data.append({
            "date": f"2026-{4 + m:02d}-{d + 1:02d}",
            "open": 2700.0 + i, "high": 2710.0 + i, "low": 2690.0 + i,
            "close": 2705.0 + i,
        })
    return {"instrument": name, "source": "KRX", "chart_type": "line", "data": data}


def _ctx(*series) -> ContextAnalysis:
    return ContextAnalysis(time_series=list(series))


def _report(chart: dict) -> ComposedReport:
    return ComposedReport(
        headline="h",
        sections=[ComposedSection(heading="시장", prose="p", charts=[chart])],
    )


def test_sparse_line_chart_densified_within_window() -> None:
    series = _daily_series(60)
    # composer 가 60일 중 4 포인트만 추려 emit (창 = 4/1 ~ 5/30 전체)
    chart = {
        "type": "line", "title": "코스피 — 3개월",
        "data": [
            {"x": "2026-04-01", "y": 2705.0},
            {"x": "2026-04-15", "y": 2719.0, "event": "관세 충격"},
            {"x": "2026-05-10", "y": 2744.0},
            {"x": "2026-05-30", "y": 2764.0},
        ],
    }
    rep = _report(chart)
    _densify_ts_charts(rep, _ctx(series))
    new = rep.sections[0].charts[0]["data"]
    assert len(new) == 60, f"일별 밀도 교체 실패: {len(new)} points"
    assert all("x" in r and "y" in r for r in new)
    # 이벤트 마커 보존 (정확 날짜 매칭).
    ev_rows = [r for r in new if r.get("event")]
    assert len(ev_rows) == 1 and ev_rows[0]["x"] == "2026-04-15"
    assert ev_rows[0]["event"] == "관세 충격"


def test_intentional_zoom_window_preserved() -> None:
    series = _daily_series(60)
    # composer 가 사건 주간 (4/10~4/14, 5거래일) 만 확대 — 창은 보존, 창 안만 densify.
    chart = {
        "type": "line", "title": "코스피 급락 주간",
        "data": [
            {"x": "2026-04-10", "y": 2714.0},
            {"x": "2026-04-12", "y": 2716.0},
            {"x": "2026-04-14", "y": 2718.0},
        ],
    }
    rep = _report(chart)
    _densify_ts_charts(rep, _ctx(series))
    new = rep.sections[0].charts[0]["data"]
    assert len(new) == 5  # 4/10·11·12·13·14 — 창 밖 55일은 안 들어옴
    assert new[0]["x"] == "2026-04-10" and new[-1]["x"] == "2026-04-14"


def test_short_date_keys_fall_back_to_full_series_with_suffix_events() -> None:
    series = _daily_series(60)
    chart = {
        "type": "line", "title": "코스피 — 3개월",
        "data": [
            {"x": "04-01", "y": 2705.0},
            {"x": "05-10", "y": 2744.0, "event": "외국인 순매수 전환"},
            {"x": "05-30", "y": 2764.0},
        ],
    }
    rep = _report(chart)
    _densify_ts_charts(rep, _ctx(series))
    new = rep.sections[0].charts[0]["data"]
    assert len(new) == 60  # 창 해석 불가 → 전체 일별 series
    ev_rows = [r for r in new if r.get("event")]
    assert len(ev_rows) == 1 and ev_rows[0]["x"].endswith("05-10")


def test_candle_chart_densified_with_full_ohlc() -> None:
    series = _daily_series(40, name="삼성전자")
    series["chart_type"] = "candle"
    chart = {
        "type": "candle", "title": "삼성전자 — 일간 OHLC",
        "data": [
            {"date": "2026-04-01", "open": 2700, "high": 2710, "low": 2690, "close": 2705},
            {"date": "2026-05-09", "open": 2738, "high": 2748, "low": 2728, "close": 2743},
        ],
    }
    rep = _report(chart)
    _densify_ts_charts(rep, _ctx(series))
    new = rep.sections[0].charts[0]["data"]
    assert len(new) == 39  # 4/1 ~ 5/9 창 안의 전 거래일
    assert all({"date", "open", "high", "low", "close"} <= set(r) for r in new)


def test_dense_chart_compact_row_and_unmatched_title_untouched() -> None:
    series = _daily_series(10)
    # ① 이미 일별 밀도 (series 와 동일 수) — 불변
    dense = {
        "type": "line", "title": "코스피",
        "data": [{"x": d["date"], "y": d["close"]} for d in series["data"]],
    }
    # ② compact strip row — 불변
    compact = {
        "type": "line", "role": "compact", "title": "코스피",
        "instrument": "코스피", "data": [{"x": "2026-04-01", "y": 1.0}, {"x": "2026-05-30", "y": 2.0}],
    }
    # ③ instrument 비매칭 title — 불변
    other = {
        "type": "line", "title": "글로벌 운임 지수",
        "data": [{"x": "2026-04-01", "y": 1.0}, {"x": "2026-05-30", "y": 2.0}],
    }
    rep = ComposedReport(headline="h", sections=[
        ComposedSection(heading="s", prose="p", charts=[dense, compact, other]),
    ])
    import copy
    before = copy.deepcopy([dense, compact, other])
    _densify_ts_charts(rep, _ctx(series))
    after = rep.sections[0].charts
    assert len(after[0]["data"]) == len(before[0]["data"])
    assert after[1]["data"] == before[1]["data"]
    assert after[2]["data"] == before[2]["data"]


def test_no_series_or_no_sections_is_noop() -> None:
    rep = _report({"type": "line", "title": "코스피", "data": [{"x": "04-01", "y": 1.0}, {"x": "04-02", "y": 2.0}]})
    _densify_ts_charts(rep, ContextAnalysis())  # time_series 없음
    assert len(rep.sections[0].charts[0]["data"]) == 2
    _densify_ts_charts(None, _ctx(_daily_series(5)))  # composed 없음 — 예외 없이 통과
