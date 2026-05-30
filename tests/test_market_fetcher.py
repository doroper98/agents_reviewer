"""v5.2.0 — market_fetcher 회귀 테스트.

HTTP 호출 모킹 — 파서·라우팅·graceful degradation 만 결정적 검증.
실 HTTP 통합 테스트는 운영 환경에서 .env 의 API key 로 별도 검증.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import patch

import pytest

from src.tools.market_fetcher import (
    INSTRUMENT_REGISTRY,
    MarketSeries,
    OHLCBar,
    _parse_ecos,
    _parse_fred,
    _parse_krx,
    fetch_many,
    fetch_market_series,
    period_to_dates,
    resolve_instrument,
)


# ─── resolve_instrument ─────────────────────────────────────────


def test_resolve_exact_registry_key() -> None:
    """v5.2.1 — KOSPI 지수는 Yahoo 로 라우팅 (pykrx index 우회)."""
    spec = resolve_instrument("KOSPI")
    assert spec is not None
    assert spec.source == "YAHOO"
    assert spec.code == "^KS11"


def test_resolve_korean_alias() -> None:
    assert resolve_instrument("코스피") is not None
    assert resolve_instrument("삼성전자") is not None
    assert resolve_instrument("국고 10년") is not None
    assert resolve_instrument("WTI 유가") is not None


def test_resolve_unknown_returns_none() -> None:
    assert resolve_instrument("비트코인") is None
    assert resolve_instrument("") is None
    assert resolve_instrument(None) is None  # type: ignore[arg-type]


def test_resolve_substring_match() -> None:
    # query 가 alias 를 포함하는 경우
    spec = resolve_instrument("미국채 1Y 수익률")
    assert spec is not None
    assert spec.code == "DGS1"


# ─── v5.6.9 미국 개별주 / 지수 ──────────────────────────────────

def test_resolve_us_stocks() -> None:
    """미국 빅테크/반도체 개별주 — Yahoo source, candle 차트."""
    cases = {
        "엔비디아": "NVDA", "NVIDIA": "NVDA",
        "테슬라": "TSLA", "Tesla": "TSLA",
        "애플": "AAPL", "Apple": "AAPL",
        "마이크로소프트": "MSFT", "Microsoft": "MSFT",
        "알파벳": "GOOGL", "구글": "GOOGL",
        "아마존": "AMZN",
        "페이스북": "META",
        "AMD": "AMD",
        "TSMC": "TSM", "대만 반도체": "TSM",
        "브로드컴": "AVGO",
    }
    for query, expected_code in cases.items():
        spec = resolve_instrument(query)
        assert spec is not None, f"{query!r} → None (등록 누락)"
        assert spec.source == "YAHOO", f"{query!r} source={spec.source}"
        assert spec.code == expected_code, f"{query!r} → {spec.code} (기대 {expected_code})"
        assert spec.chart_type == "candle"


def test_resolve_us_indices() -> None:
    """미국 지수 — Yahoo source, line 차트."""
    for query, code in [("S&P 500", "^GSPC"), ("나스닥", "^IXIC"),
                        ("필라델피아 반도체", "^SOX")]:
        spec = resolve_instrument(query)
        assert spec is not None, f"{query!r} → None"
        assert spec.source == "YAHOO"
        assert spec.code == code
        assert spec.chart_type == "line"


def test_resolve_us_stock_in_topic_phrase() -> None:
    """본문 구절 안에 종목명이 있어도 substring 매치."""
    assert resolve_instrument("엔비디아 신제품 발표").code == "NVDA"  # type: ignore[union-attr]
    assert resolve_instrument("아마존 AWS 실적 호조").code == "AMZN"  # type: ignore[union-attr]


# ─── period_to_dates ────────────────────────────────────────────


def test_period_to_dates_default_3m() -> None:
    start, end = period_to_dates("3M", anchor=date(2026, 5, 15))
    assert end == date(2026, 5, 15)
    assert (end - start).days == 92


def test_period_to_dates_1y() -> None:
    start, end = period_to_dates("1Y", anchor=date(2026, 5, 15))
    assert (end - start).days == 365


def test_period_to_dates_3y() -> None:
    start, end = period_to_dates("3Y", anchor=date(2026, 5, 15))
    assert (end - start).days == 1095


def test_period_to_dates_unknown_falls_back_3m() -> None:
    start, end = period_to_dates("UNKNOWN", anchor=date(2026, 5, 15))
    assert (end - start).days == 92


# ─── 파서 ────────────────────────────────────────────────────────


def test_parse_fred_skips_dot_placeholder() -> None:
    """FRED 휴장일은 value='.' — skip."""
    body = {
        "observations": [
            {"date": "2026-05-13", "value": "104.32"},
            {"date": "2026-05-14", "value": "."},
            {"date": "2026-05-15", "value": "104.58"},
        ]
    }
    bars = _parse_fred(body)
    assert len(bars) == 2
    assert bars[0].close == 104.32
    assert bars[1].date == "2026-05-15"


def test_parse_fred_empty_returns_empty() -> None:
    assert _parse_fred({}) == []
    assert _parse_fred({"observations": []}) == []


def test_parse_ecos_handles_error_response() -> None:
    body = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다"}}
    assert _parse_ecos(body) == []


def test_parse_ecos_iso_date_conversion() -> None:
    """ECOS TIME='20260515' → date='2026-05-15'."""
    body = {
        "StatisticSearch": {
            "row": [
                {"TIME": "20260513", "DATA_VALUE": "3.32"},
                {"TIME": "20260515", "DATA_VALUE": "3.35"},
            ]
        }
    }
    bars = _parse_ecos(body)
    assert len(bars) == 2
    assert bars[0].date == "2026-05-13"
    assert bars[0].close == 3.32
    assert bars[1].date == "2026-05-15"


def test_parse_ecos_skips_dot_value() -> None:
    body = {
        "StatisticSearch": {
            "row": [
                {"TIME": "20260513", "DATA_VALUE": "."},
                {"TIME": "20260515", "DATA_VALUE": "3.35"},
            ]
        }
    }
    bars = _parse_ecos(body)
    assert len(bars) == 1
    assert bars[0].date == "2026-05-15"


def test_parse_krx_ohlc_individual_stock() -> None:
    """KRX 개별주 응답 — TDD_OPNPRC / TDD_HGPRC / TDD_LWPRC / TDD_CLSPRC."""
    body = {
        "output": [
            {
                "TRD_DD": "2026/05/15",
                "TDD_OPNPRC": "94,000",
                "TDD_HGPRC": "95,500",
                "TDD_LWPRC": "93,800",
                "TDD_CLSPRC": "93,800",
                "ACC_TRDVOL": "18,500,000",
            },
            {
                "TRD_DD": "2026/05/14",
                "TDD_OPNPRC": "93,000",
                "TDD_HGPRC": "94,200",
                "TDD_LWPRC": "92,800",
                "TDD_CLSPRC": "94,000",
                "ACC_TRDVOL": "15,500,000",
            },
        ]
    }
    bars = _parse_krx(body)
    # 시간 오름차순 정렬됐는지
    assert len(bars) == 2
    assert bars[0].date == "2026-05-14"
    assert bars[1].date == "2026-05-15"
    assert bars[1].close == 93800.0
    assert bars[1].volume == 18500000.0


def test_parse_krx_ohlc_index() -> None:
    """KRX 지수 응답 — OPNPRC_IDX / CLSPRC_IDX."""
    body = {
        "output": [
            {
                "TRD_DD": "2026-05-15",
                "OPNPRC_IDX": "7,900.00",
                "HGPRC_IDX": "8,050.00",
                "LWPRC_IDX": "7,890.00",
                "CLSPRC_IDX": "8,002.66",
            },
        ]
    }
    bars = _parse_krx(body)
    assert len(bars) == 1
    assert bars[0].close == 8002.66


def test_parse_krx_skips_zero_close() -> None:
    """휴장일·결측 (close=0) 은 skip."""
    body = {
        "output": [
            {"TRD_DD": "2026-05-15", "TDD_OPNPRC": "0", "TDD_HGPRC": "0",
             "TDD_LWPRC": "0", "TDD_CLSPRC": "0", "ACC_TRDVOL": "0"},
        ]
    }
    assert _parse_krx(body) == []


def test_parse_krx_handles_comma_separated_numbers() -> None:
    body = {
        "output": [
            {"TRD_DD": "2026-05-15",
             "TDD_OPNPRC": "1,234,567",
             "TDD_HGPRC": "1,234,567",
             "TDD_LWPRC": "1,234,567",
             "TDD_CLSPRC": "1,234,567"},
        ]
    }
    bars = _parse_krx(body)
    assert bars[0].close == 1234567.0


# ─── Graceful degradation ───────────────────────────────────────


class _FakeConfig:
    fred_api_key = ""
    ecos_api_key = ""
    krx_api_key = ""


def test_fetch_market_series_missing_key_returns_empty() -> None:
    """API key 없으면 빈 series + warning (no exception)."""
    async def run():
        return await fetch_market_series("WTI", "3M", config=_FakeConfig())
    result = asyncio.run(run())
    assert isinstance(result, MarketSeries)
    assert result.instrument == "WTI 유가"
    assert result.source == "FRED"
    assert result.data == []


def test_fetch_market_series_unknown_instrument_returns_empty() -> None:
    async def run():
        return await fetch_market_series("아무말", "3M", config=_FakeConfig())
    result = asyncio.run(run())
    assert result.data == []


def test_fetch_many_handles_mixed_unknown_and_known() -> None:
    """일부 unknown 이어도 나머지 진행, 모두 빈 data 로 결과 list 반환."""
    async def run():
        return await fetch_many(
            ["KOSPI", "비트코인", "WTI"], "3M", config=_FakeConfig(),
        )
    results = asyncio.run(run())
    assert len(results) == 3
    # 모두 키 없거나 미등록 → data 비어있음. 단 instrument 이름은 유지
    assert all(r.data == [] for r in results)


def test_fetch_many_empty_input() -> None:
    async def run():
        return await fetch_many([], "3M", config=_FakeConfig())
    assert asyncio.run(run()) == []


# ─── INSTRUMENT_REGISTRY sanity ─────────────────────────────────


def test_registry_all_sources_valid() -> None:
    valid_sources = {"KRX", "FRED", "ECOS", "YAHOO"}
    for key, spec in INSTRUMENT_REGISTRY.items():
        assert spec.source in valid_sources, f"{key}: bad source {spec.source}"
        assert spec.chart_type in {"line", "candle", "area"}, f"{key}: bad chart_type"
        assert spec.code, f"{key}: empty code"


def test_registry_covers_6_user_specified() -> None:
    """사용자 결정 6 종목 모두 매핑."""
    expected = ["코스피", "삼성전자", "달러인덱스", "국고 10년", "미국채 1Y", "WTI"]
    for q in expected:
        assert resolve_instrument(q) is not None, f"{q} 매핑 누락"


def test_registry_chart_type_convention() -> None:
    """사용자 합의 — 지수=line / 개별주=candle / 원자재=area."""
    assert resolve_instrument("코스피").chart_type == "line"
    assert resolve_instrument("삼성전자").chart_type == "candle"
    assert resolve_instrument("WTI").chart_type == "area"
    assert resolve_instrument("금").chart_type == "area"
    assert resolve_instrument("국고 10년").chart_type == "line"


def test_kospi_routed_to_yahoo() -> None:
    """v5.2.1 — 지수는 Yahoo Finance 로 (pykrx index 우회)."""
    spec = resolve_instrument("코스피")
    assert spec is not None
    assert spec.source == "YAHOO"
    assert spec.code == "^KS11"


def test_dxy_routed_to_yahoo_ice_ticker() -> None:
    """v5.2.6 — DXY 는 진짜 ICE 달러인덱스 (Yahoo DX-Y.NYB) 로 가져온다.

    이전엔 FRED/DTWEXBGS (Fed Broad TWI, 2006-01=100, 117~125 레인지) 를
    "DXY" 로 라벨링해 시장 통념과 충돌. ICE U.S. Dollar Index
    (1973-03=100, 6-통화 고정 바스켓, 99~110 레인지) 로 교체.
    """
    spec = resolve_instrument("달러인덱스")
    assert spec is not None
    assert spec.source == "YAHOO"
    assert spec.code == "DX-Y.NYB"
    # DTWEXBGS 회귀 방지 — Fed Broad TWI 는 DXY 가 아니다.
    assert spec.code != "DTWEXBGS"


def test_kosdaq_routed_to_yahoo() -> None:
    spec = resolve_instrument("코스닥")
    assert spec is not None
    assert spec.source == "YAHOO"
    assert spec.code == "^KQ11"


def test_samsung_still_krx() -> None:
    """개별주는 pykrx 그대로."""
    spec = resolve_instrument("삼성전자")
    assert spec is not None
    assert spec.source == "KRX"
    assert spec.code == "005930"
