"""시장 등락 종목 수(breadth) 집계·요약 단위 테스트 — v7.9.0.

네트워크 없이 순수 함수(count_breadth/summarize_market/build_key_figures/build_charts/
corr_lagged)를 KRX MDCSTAT01501 형태 합성 rows 로 검증.
"""

from datetime import date, timedelta

from src.tools.breadth_fetcher import (
    DailyBreadth,
    count_breadth,
    summarize_market,
    build_key_figures,
    build_charts,
    corr_lagged,
    _pearson,
    _business_days,
)


def test_count_breadth_by_fluct_sign():
    rows = [
        {"TDD_CLSPRC": "5,400", "FLUC_RT": "1.31"},    # up
        {"TDD_CLSPRC": "2,365", "FLUC_RT": "-0.21"},   # down
        {"TDD_CLSPRC": "12,000", "FLUC_RT": "0.00"},   # flat
        {"TDD_CLSPRC": "0", "FLUC_RT": "5.0"},          # 거래정지(제외)
        {"TDD_CLSPRC": "100", "CMPPREVDD_PRC": "-3"},   # FLUC_RT 없음 → 폴백 down
    ]
    db = count_breadth(rows, "KOSPI", "2026-06-17")
    assert db is not None
    assert db.up == 1
    assert db.down == 2
    assert db.flat == 1
    assert db.total == 4
    assert abs(db.down_ratio - 0.5) < 1e-9


def test_count_breadth_empty_is_none():
    assert count_breadth([], "KOSPI", "2026-06-17") is None
    assert count_breadth([{"TDD_CLSPRC": "0", "FLUC_RT": "1"}], "KOSPI", "d") is None


def _make_series(market: str, n: int, down_ratios: list[float]) -> list[DailyBreadth]:
    base = date(2026, 1, 1)
    out = []
    for i, dr in enumerate(down_ratios[-n:]):
        total = 1000
        down = int(round(dr * total))
        up = total - down
        out.append(DailyBreadth(market, (base + timedelta(days=i)).isoformat(),
                                up=up, down=down, flat=0, total=total))
    return out


def test_summarize_trend_widening():
    # 최근 5일 하락비율이 20일 평균보다 높음 → '확대'
    drs = [0.4] * 15 + [0.7] * 5
    view = summarize_market(_make_series("KOSPI", 20, drs))
    assert view is not None
    assert view.trend == "확대"
    assert view.dr_avg5 > view.dr_avg20
    assert abs(view.dr_last - 70.0) < 1e-6


def test_summarize_trend_easing():
    drs = [0.6] * 15 + [0.3] * 5
    view = summarize_market(_make_series("KOSDAQ", 20, drs))
    assert view is not None
    assert view.trend == "완화"


def test_summarize_empty_none():
    assert summarize_market([]) is None


def test_corr_insufficient_returns_none():
    series = _make_series("KOSPI", 10, [0.5] * 10)
    assert corr_lagged(series, {"2026-01-01": 100.0}) is None  # 표본 부족


def test_pearson_sign():
    # 완전 음의 선형 관계 → -1.
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    r = _pearson(xs, ys)
    assert r is not None and abs(r - (-1.0)) < 1e-9
    # 완전 양의 관계 → +1.
    assert abs(_pearson(xs, [2 * x for x in xs]) - 1.0) < 1e-9
    # 분산 0 → None.
    assert _pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_corr_lagged_returns_value_in_range_with_enough_data():
    # 충분한 표본 + 지수 데이터가 있으면 [-1,1] 범위 실수 반환(부호는 데이터 의존).
    n = 60
    base = date(2026, 1, 1)
    series = []
    closes = {}
    price = 100.0
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        total = 1000
        down = 300 + (i % 10) * 40           # 0.30~0.66 사이 변동
        series.append(DailyBreadth("KOSPI", d, up=total - down, down=down, flat=0, total=total))
        closes[d] = price
        price *= 1.001
    corr = corr_lagged(series, closes, smooth=5, lag=5)
    assert corr is not None
    assert -1.0 <= corr <= 1.0


def test_build_key_figures_and_charts():
    drs = [0.4] * 15 + [0.65] * 5
    v = summarize_market(_make_series("KOSPI", 20, drs))
    assert v is not None
    kfs = build_key_figures([v], "2026-06-17")
    assert kfs and all({"label", "value", "context"} <= set(kf) for kf in kfs)
    assert any("등락 종목 수" in kf["label"] for kf in kfs)
    charts = build_charts([v])
    assert charts and charts[0]["type"] == "line"
    assert len(charts[0]["data"]) == 20
    assert all("x" in p and "y" in p for p in charts[0]["data"])


def test_build_charts_skips_short_series():
    v = summarize_market(_make_series("KOSPI", 3, [0.5, 0.5, 0.5]))
    assert v is not None
    assert build_charts([v], min_points=5) == []


def test_business_days_weekdays_only():
    # 2026-06-17 은 수요일.
    days = _business_days(date(2026, 6, 17), 5)
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days)
    assert days[-1] == date(2026, 6, 17)
