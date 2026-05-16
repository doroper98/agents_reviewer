"""시계열 차트 takeaway 회귀 가드 (v5.2.7).

기능 SSOT — 함께 갱신:
- ``src/orchestrator.py:_format_ts_takeaway`` (포매터 본체)
- ``src/orchestrator.py:_build_ts_chart`` (caller — instrument 인자 전달)
- ``scripts/patch_report.py:--regenerate-ts-takeaways`` (retro fix flag)

본 회귀의 catch:
1. v5.2.7 이전: ``context.summary.split(".")[0]`` 1순위 → ① 모든 차트가 동일
   문장 (summary 는 보고서 전역 1개), ② 소수점에서 절단
   ("...5월 15일 4.52%로 상승" → "...5월 15일 4"). 본 테스트가 두 경로 모두 lock.
2. instrument 별 takeaway 가 *다르게* 나오는지 검증 (같은 함수, 다른 데이터).
3. 빈 데이터 / 단일 포인트 → 빈 문자열 반환 (graceful).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.orchestrator import _format_ts_takeaway


def _ctx(summary: str = ""):
    """summary 만 가진 minimal context — 회귀 함수는 이 필드를 *무시* 해야."""
    return SimpleNamespace(summary=summary)


def test_decimal_point_no_longer_truncates_takeaway() -> None:
    """v5.2.7 회귀 가드: summary 의 소수점에서 끊겨 '...5월 15일 4' 같은
    절단 문자열이 takeaway 로 들어가던 버그.

    이전 구현: ``summary.split(".")[0]`` → "4.52%" 의 "." 에서 split.
    현재 구현: summary 무시, 데이터 기반 결정적 생성 → 절단 불가.
    """
    summary_with_decimal = "미국 10년물 국채 금리가 5월 15일 4.52%로 상승했다"
    data = [{"x": "2026-04-15", "y": 4.30}, {"x": "2026-05-15", "y": 4.52}]
    out = _format_ts_takeaway(data, "line", _ctx(summary_with_decimal),
                              instrument="미국채 10Y")
    # 절단 회귀 차단 — summary 의 텍스트가 그대로 들어가면 안 됨.
    assert "5월 15일 4" not in out or "변동폭" in out
    # 데이터 기반 키워드 검증.
    assert "미국채 10Y" in out
    assert "4.52" in out  # 마지막 값
    assert "%" in out


def test_takeaway_differs_per_instrument_with_same_context() -> None:
    """v5.2.7 회귀 가드: 동일 context.summary 라도 차트마다 *다른* takeaway.

    이전 구현은 summary 1순위라 모든 차트가 같은 문장. 현재는 instrument +
    data 기반이라 두 차트가 같은 takeaway 일 확률 ≈ 0.
    """
    shared_ctx = _ctx("미국 매크로 변화. 달러 강세 지속.")
    dxy_data = [
        {"x": "2026-02-12", "y": 99.50},
        {"x": "2026-03-15", "y": 101.20},
        {"x": "2026-05-15", "y": 103.40},
    ]
    us10y_data = [
        {"x": "2026-02-12", "y": 4.30},
        {"x": "2026-03-15", "y": 4.45},
        {"x": "2026-05-15", "y": 4.52},
    ]
    t_dxy = _format_ts_takeaway(dxy_data, "line", shared_ctx, instrument="달러인덱스")
    t_us = _format_ts_takeaway(us10y_data, "line", shared_ctx, instrument="미국채 10Y")
    assert t_dxy != t_us
    assert "달러인덱스" in t_dxy
    assert "미국채 10Y" in t_us
    # 같은 summary 가 두 문장 안에 그대로 들어가지 않음.
    assert "달러 강세 지속" not in t_dxy
    assert "달러 강세 지속" not in t_us


def test_takeaway_includes_direction_and_range() -> None:
    """포매터 계약: 방향 (상승/하락/횡보) + 범위 (저~고) + 마지막값 + 변동폭."""
    rising = [{"x": "2026-04-01", "y": 100.0}, {"x": "2026-05-01", "y": 105.0}]
    out = _format_ts_takeaway(rising, "line", _ctx(), instrument="테스트")
    assert "상승" in out
    assert "100.00" in out  # 최저
    assert "105.00" in out  # 최고
    assert "변동폭" in out

    falling = [{"x": "2026-04-01", "y": 105.0}, {"x": "2026-05-01", "y": 100.0}]
    out_f = _format_ts_takeaway(falling, "line", _ctx(), instrument="테스트")
    assert "하락" in out_f

    flat = [{"x": "2026-04-01", "y": 100.00}, {"x": "2026-05-01", "y": 100.05}]
    out_flat = _format_ts_takeaway(flat, "line", _ctx(), instrument="테스트")
    assert "횡보" in out_flat


def test_takeaway_empty_or_singleton_returns_empty_string() -> None:
    """graceful — fetch 실패 / 1포인트만 있는 series 면 빈 문자열."""
    assert _format_ts_takeaway([], "line", _ctx(), instrument="x") == ""
    assert _format_ts_takeaway([{"x": "2026-05-15", "y": 100.0}], "line",
                                _ctx(), instrument="x") == ""


def test_takeaway_candle_chart_uses_close_field() -> None:
    """candle 차트는 ``close`` 필드 (line 의 ``y`` 가 아닌) 를 읽는다."""
    candle_data = [
        {"date": "2026-04-01", "open": 70000, "high": 71000, "low": 69500, "close": 70500},
        {"date": "2026-05-01", "open": 70500, "high": 73000, "low": 70200, "close": 72000},
    ]
    out = _format_ts_takeaway(candle_data, "candle", _ctx(), instrument="삼성전자")
    assert "삼성전자" in out
    # 1000 이상은 ","-grouped 정수.
    assert "70,500" in out
    assert "72,000" in out
    assert "상승" in out


def test_takeaway_does_not_depend_on_summary_field() -> None:
    """v5.2.7 핵심 계약: context.summary 변경해도 takeaway 동일.

    이전 구현은 summary 가 1순위라 같은 데이터 + 다른 summary 면 takeaway
    달라졌음. 현재는 summary 가 takeaway 에 영향 X.
    """
    data = [{"x": "2026-04-01", "y": 100.0}, {"x": "2026-05-01", "y": 105.0}]
    a = _format_ts_takeaway(data, "line", _ctx("summary A"), instrument="X")
    b = _format_ts_takeaway(data, "line", _ctx("완전히 다른 summary 텍스트"), instrument="X")
    c = _format_ts_takeaway(data, "line", _ctx(""), instrument="X")
    assert a == b == c
