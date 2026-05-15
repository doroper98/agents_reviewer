"""Market data fetcher — KRX (Korean index/equity) + FRED (US macro) + ECOS (BOK).

v5.2.0 — 시계열 데이터 수집. ContextAnalyst 가 LLM 출력에 ``instruments_mentioned``
필드를 emit 하면, orchestrator 가 본 모듈을 호출해 ``ContextAnalysis.time_series``
를 채움. composer 가 그 데이터를 받아 line / candle / area 차트로 emit.

[Fetcher 매핑]

| 종목                  | Source | Code                  | 차트 기본 |
|----------------------|--------|-----------------------|----------|
| KOSPI                | KRX    | 1001 (index)          | line     |
| KOSDAQ               | KRX    | 2001 (index)          | line     |
| 삼성전자              | KRX    | 005930                | candle   |
| SK하이닉스            | KRX    | 000660                | candle   |
| 달러인덱스 (DXY)      | FRED   | DTWEXBGS              | line     |
| 미국채 1Y             | FRED   | DGS1                  | line     |
| 미국채 10Y            | FRED   | DGS10                 | line     |
| WTI 유가              | FRED   | DCOILWTICO            | area     |
| 금                   | FRED   | GOLDAMGBD228NLBM      | area     |
| 국고채 10Y            | ECOS   | 817Y002/010210000     | line     |
| 원/달러 환율          | ECOS   | 731Y001/0000001       | line     |

[Public API]
    fetch_market_series(instrument, period, config, anchor_date=None) -> MarketSeries
    fetch_many(instruments, ...) -> list[MarketSeries]
    resolve_instrument(query) -> InstrumentSpec | None

[Graceful degradation]
- API key 누락 → 빈 series + warning log (보고서 정상 진행)
- HTTP error → 빈 series + warning log
- 미등록 instrument → 빈 series + warning log

[환경변수]
- ``FRED_API_KEY``: research.stlouisfed.org/docs/api/api_key.html
- ``ECOS_API_KEY``: ecos.bok.or.kr/api/ (한국은행 회원가입 후 발급)
- ``KRX_API_KEY``: (현재 미사용 — KRX public endpoint 무인증)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import aiohttp
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─── 종목 레지스트리 ──────────────────────────────────────────


@dataclass(frozen=True)
class InstrumentSpec:
    """instrument 별 fetch 라우팅 + 표시 메타."""

    name: str                       # 표시명 (보고서/차트에 노출)
    source: Literal["KRX", "FRED", "ECOS"]
    code: str                       # source 별 ticker / series id
    chart_type: Literal["line", "candle", "area"] = "line"
    unit: str = ""                  # "%", "원", "$" 등
    aliases: tuple[str, ...] = ()   # LLM 출력의 한글 표현 매칭용


INSTRUMENT_REGISTRY: dict[str, InstrumentSpec] = {
    # ── KRX 지수 ──
    "KOSPI": InstrumentSpec(
        name="코스피", source="KRX", code="1001",
        chart_type="line",
        aliases=("코스피", "KOSPI", "한국 증시 종합", "한국증시", "한국 증시"),
    ),
    "KOSDAQ": InstrumentSpec(
        name="코스닥", source="KRX", code="2001",
        chart_type="line",
        aliases=("코스닥", "KOSDAQ"),
    ),
    # ── KRX 개별주 ──
    "005930": InstrumentSpec(
        name="삼성전자", source="KRX", code="005930",
        chart_type="candle", unit="원",
        aliases=("삼성전자", "삼전", "Samsung Electronics"),
    ),
    "000660": InstrumentSpec(
        name="SK하이닉스", source="KRX", code="000660",
        chart_type="candle", unit="원",
        aliases=("SK하이닉스", "SK 하이닉스", "하이닉스"),
    ),
    # ── FRED 매크로 ──
    "DXY": InstrumentSpec(
        name="달러인덱스", source="FRED", code="DTWEXBGS",
        chart_type="line",
        aliases=("달러인덱스", "달러 인덱스", "DXY"),
    ),
    "DGS1": InstrumentSpec(
        name="미국채 1Y", source="FRED", code="DGS1",
        chart_type="line", unit="%",
        aliases=("미국채 1년", "미국채 1Y", "UST1Y", "US 1Y"),
    ),
    "DGS10": InstrumentSpec(
        name="미국채 10Y", source="FRED", code="DGS10",
        chart_type="line", unit="%",
        aliases=("미국채 10년", "미국채 10Y", "UST10Y", "US 10Y"),
    ),
    "WTI": InstrumentSpec(
        name="WTI 유가", source="FRED", code="DCOILWTICO",
        chart_type="area", unit="$",
        aliases=("WTI", "WTI 유가", "서부텍사스원유", "서부 텍사스 원유"),
    ),
    "GOLD": InstrumentSpec(
        name="금", source="FRED", code="GOLDAMGBD228NLBM",
        chart_type="area", unit="$",
        aliases=("금", "금 가격", "GOLD", "골드"),
    ),
    # ── ECOS 한국 매크로 ──
    "KTB10Y": InstrumentSpec(
        name="국고채 10Y", source="ECOS", code="817Y002/010210000",
        chart_type="line", unit="%",
        aliases=("국고 10년", "국고채 10년", "국고채 10Y", "국고 10Y", "KTB10Y"),
    ),
    "USDKRW": InstrumentSpec(
        name="원/달러 환율", source="ECOS", code="731Y001/0000001",
        chart_type="line", unit="원",
        aliases=("원달러", "원/달러", "원/달러 환율", "환율", "USD/KRW", "USDKRW"),
    ),
}


def resolve_instrument(query: str) -> InstrumentSpec | None:
    """LLM 출력의 instrument 문자열 → InstrumentSpec.

    1) registry key 정확 매치 → 즉시 반환
    2) alias 정확 매치 (대소문자 무시)
    3) alias 가 query 안에 포함 또는 query 가 alias 안에 포함

    매치 없으면 None. 보고서 진행은 정상.
    """
    q = (query or "").strip()
    if not q:
        return None
    if q in INSTRUMENT_REGISTRY:
        return INSTRUMENT_REGISTRY[q]
    q_low = q.lower()
    # exact alias
    for spec in INSTRUMENT_REGISTRY.values():
        for alias in spec.aliases:
            if alias.lower() == q_low:
                return spec
    # substring alias (한쪽 방향만 허용 — 너무 짧은 alias 가 다른 단어를 잡지 않게)
    for spec in INSTRUMENT_REGISTRY.values():
        for alias in spec.aliases:
            if len(alias) >= 3 and alias.lower() in q_low:
                return spec
    return None


# ─── 모델 ────────────────────────────────────────────────────


class OHLCBar(BaseModel):
    """일간 OHLC 한 행. close-only 소스 (FRED/ECOS) 는 open=high=low=close."""

    date: str            # "YYYY-MM-DD"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float
    volume: float | None = None


class MarketSeries(BaseModel):
    """한 instrument 의 시계열 + 메타."""

    instrument: str               # 표시명 (e.g. "코스피")
    source: str = ""              # "KRX" / "FRED" / "ECOS"
    code: str = ""
    unit: str = ""
    chart_type: str = "line"      # composer 가 참고하는 기본 차트 type
    start_date: str = ""
    end_date: str = ""
    data: list[OHLCBar] = Field(default_factory=list)


# ─── Fetcher 구현 ────────────────────────────────────────────


class FREDFetcher:
    """FRED — U.S. Federal Reserve Economic Data.

    Daily close 만 반환 (no OHLC). https://fred.stlouisfed.org/docs/api/
    """

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, code: str, start: date, end: date) -> list[OHLCBar]:
        if not self.api_key:
            logger.warning("[market_fetcher] FRED_API_KEY 없음 — %s 스킵", code)
            return []
        params = {
            "series_id": code,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.BASE_URL, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(
                            "[market_fetcher] FRED %s HTTP %d: %s",
                            code, resp.status, text[:200],
                        )
                        return []
                    body = await resp.json()
        except Exception as e:
            logger.warning("[market_fetcher] FRED %s fetch error: %s", code, e)
            return []
        return _parse_fred(body)


class ECOSFetcher:
    """한국은행 ECOS — Korean macro statistics.

    Daily series 만 사용. https://ecos.bok.or.kr/api/
    code 형식: ``STAT_CODE/ITEM_CODE`` (e.g. ``817Y002/010210000``)
    """

    BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, code: str, start: date, end: date) -> list[OHLCBar]:
        if not self.api_key:
            logger.warning("[market_fetcher] ECOS_API_KEY 없음 — %s 스킵", code)
            return []
        parts = (code or "").split("/")
        if not parts or not parts[0]:
            return []
        stat_code = parts[0]
        item_code = parts[1] if len(parts) > 1 else ""
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        url = (
            f"{self.BASE_URL}/{self.api_key}/json/kr/1/10000/"
            f"{stat_code}/D/{start_str}/{end_str}"
        )
        if item_code:
            url += f"/{item_code}"
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(
                            "[market_fetcher] ECOS %s HTTP %d: %s",
                            code, resp.status, text[:200],
                        )
                        return []
                    body = await resp.json(content_type=None)
        except Exception as e:
            logger.warning("[market_fetcher] ECOS %s fetch error: %s", code, e)
            return []
        return _parse_ecos(body)


class KRXFetcher:
    """KRX (Korea Exchange) — 한국 지수·개별주 OHLC.

    KRX 정보데이터시스템 public endpoint. 무인증 (rate limit 있음).

    [세션 처리 — v5.2.0]
    KRX 는 cookie/session 기반. POST 전에 main page GET 으로 JSESSIONID 등
    세션 쿠키를 먼저 받아야 함. 안 그러면 HTTP 400 + body "LOGOUT" 으로 실패.
    """

    BASE_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    WARMUP_URL = "http://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key  # forward-compat, 현재 미사용

    async def fetch(self, code: str, start: date, end: date) -> list[OHLCBar]:
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        is_index = len(code) == 4
        if is_index:
            # 지수 일별 시세 — pykrx 와 동일 payload 구조.
            idx_market = "1" if code.startswith("1") else "2"  # 1=KOSPI 계열, 2=KOSDAQ 계열
            payload = {
                "bld": "dbms/MDC/STAT/standard/MDCSTAT00301",
                "indIdx": idx_market,
                "indIdx2": code,
                "strtDd": start_str,
                "endDd": end_str,
                "share": "1",
                "money": "1",
                "csvxls_isNo": "false",
                "locale": "ko_KR",
            }
        else:
            isin = _ISIN_MAP.get(code) or await _lookup_isin(code)
            if not isin:
                logger.warning(
                    "[market_fetcher] KRX 종목코드 %s 의 ISIN 미해결 — _ISIN_MAP 확장 또는 search endpoint 실패",
                    code,
                )
                return []
            # cache 갱신 (다음 호출 빠르게)
            _ISIN_MAP[code] = isin
            payload = {
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01701",
                "isuCd": isin,
                "strtDd": start_str,
                "endDd": end_str,
                "adjStkPrc_check": "Y",
                "adjStkPrc": "2",
                "share": "1",
                "money": "1",
                "csvxls_isNo": "false",
                "locale": "ko_KR",
            }
        headers = {
            "User-Agent": self.UA,
            "Referer": "http://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "http://data.krx.co.kr",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            # cookie_jar 가 세션 쿠키 (JSESSIONID 등) 를 자동으로 warm-up 응답에서
            # 가져와 다음 POST 에 첨부. unsafe=True 는 IP 호스트 / 비-canonical
            # 도메인 처리 호환용 (KRX 는 FQDN 이라 사실 불필요하지만 안전망).
            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
                # 1) Warm-up GET — 세션 쿠키 확보. 실패해도 본 요청은 시도.
                try:
                    async with session.get(
                        self.WARMUP_URL,
                        headers={"User-Agent": self.UA},
                        allow_redirects=True,
                    ) as warmup:
                        await warmup.read()
                except Exception as e:
                    logger.debug(
                        "[market_fetcher] KRX warmup failed (계속 시도): %s", e,
                    )
                # 2) Main POST
                async with session.post(
                    self.BASE_URL, data=payload, headers=headers,
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(
                            "[market_fetcher] KRX %s HTTP %d: %s",
                            code, resp.status, text[:200],
                        )
                        return []
                    body = await resp.json(content_type=None)
        except Exception as e:
            logger.warning("[market_fetcher] KRX %s fetch error: %s", code, e)
            return []
        return _parse_krx(body)


# 종목코드 → ISIN. KRX OHLC API 가 isuCd 로 ISIN 을 요구. 자주 쓰는 종목 *seed*
# 하드코딩 + `_lookup_isin` 동적 조회 결과를 cache 로 채움 (v5.2.0).
_ISIN_MAP: dict[str, str] = {
    "005930": "KR7005930003",   # 삼성전자
    "000660": "KR7000660001",   # SK하이닉스
    "035420": "KR7035420009",   # NAVER
    "035720": "KR7035720002",   # 카카오
    "207940": "KR7207940008",   # 삼성바이오로직스
    "005380": "KR7005380001",   # 현대차
    "051910": "KR7051910008",   # LG화학
    "006400": "KR7006400006",   # 삼성SDI
}


async def _lookup_isin(stock_code: str) -> str | None:
    """KRX 종목 search endpoint 로 6자리 코드 → ISIN 동적 조회.

    KRX 의 종목 자동완성 API. 무인증, JSON 응답. 실패 시 None.
    """
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        return None
    search_url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    payload = {
        "bld": "dbms/comm/finder/finder_stkisu",
        "mktsel": "ALL",
        "searchText": stock_code,
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "http://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(search_url, data=payload, headers=headers) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json(content_type=None)
    except Exception as e:
        logger.warning("[market_fetcher] KRX ISIN lookup %s failed: %s", stock_code, e)
        return None
    rows = body.get("block1") or body.get("output") or []
    for r in rows:
        if (r.get("short_code") or "").endswith(stock_code) or r.get("shotCode") == stock_code:
            return r.get("full_code") or r.get("isuCd") or None
    # 마지막 fallback — 첫 row 의 full_code
    if rows:
        return rows[0].get("full_code") or rows[0].get("isuCd") or None
    return None


# ─── 파서 (모듈 레벨 — 테스트 용이성) ──────────────────────────


def _parse_fred(body: dict) -> list[OHLCBar]:
    """FRED API response → OHLCBar list (close only)."""
    obs = body.get("observations") or []
    out: list[OHLCBar] = []
    for o in obs:
        val_str = o.get("value")
        if not val_str or val_str == ".":
            continue
        try:
            v = float(val_str)
        except (ValueError, TypeError):
            continue
        d = o.get("date")
        if not d:
            continue
        out.append(OHLCBar(date=d, open=v, high=v, low=v, close=v))
    return out


def _parse_ecos(body: dict) -> list[OHLCBar]:
    """ECOS API response → OHLCBar list (close only).

    error format: ``{"RESULT": {"CODE": "...", "MESSAGE": "..."}}``
    success format: ``{"StatisticSearch": {"row": [{"TIME": "20260515", "DATA_VALUE": "3.32"}]}}``
    """
    if "RESULT" in body and not body.get("StatisticSearch"):
        logger.warning("[market_fetcher] ECOS error: %s", body["RESULT"])
        return []
    rows = (body.get("StatisticSearch") or {}).get("row") or []
    out: list[OHLCBar] = []
    for r in rows:
        d_str = (r.get("TIME") or "").strip()
        val_str = r.get("DATA_VALUE")
        if not d_str or val_str in (None, "", "."):
            continue
        try:
            v = float(val_str)
        except (ValueError, TypeError):
            continue
        if len(d_str) == 8:
            d_iso = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
        else:
            d_iso = d_str
        out.append(OHLCBar(date=d_iso, open=v, high=v, low=v, close=v))
    return out


def _parse_krx(body: dict) -> list[OHLCBar]:
    """KRX API response → OHLCBar list (full OHLC + volume).

    KRX 응답이 종목/지수에 따라 필드명이 약간 달라 둘 다 처리:
    - 개별주:  TDD_OPNPRC / TDD_HGPRC / TDD_LWPRC / TDD_CLSPRC / ACC_TRDVOL
    - 지수:    OPNPRC_IDX / HGPRC_IDX / LWPRC_IDX / CLSPRC_IDX / ACC_TRDVOL
    """
    rows = body.get("output") or []
    out: list[OHLCBar] = []
    for r in rows:
        d_str = r.get("TRD_DD") or r.get("TRD_DT") or ""
        if not d_str:
            continue
        d_iso = d_str.replace("/", "-").replace(".", "-")
        try:
            o = _to_float(r.get("TDD_OPNPRC") or r.get("OPNPRC_IDX") or r.get("OPN_PRC"))
            h = _to_float(r.get("TDD_HGPRC")  or r.get("HGPRC_IDX")  or r.get("HG_PRC"))
            l = _to_float(r.get("TDD_LWPRC")  or r.get("LWPRC_IDX")  or r.get("LW_PRC"))
            c = _to_float(r.get("TDD_CLSPRC") or r.get("CLSPRC_IDX") or r.get("CLS_PRC"))
        except (ValueError, TypeError):
            continue
        if c <= 0:
            continue
        # OHL 가 0 으로 들어오면 close 로 대체 (지수 closeOnly fallback)
        if o <= 0: o = c
        if h <= 0: h = c
        if l <= 0: l = c
        vol = _to_float(r.get("ACC_TRDVOL"), default=None)
        out.append(OHLCBar(date=d_iso, open=o, high=h, low=l, close=c, volume=vol))
    # KRX 는 최신 → 과거 순서 — 시간 오름차순 정렬
    out.sort(key=lambda b: b.date)
    return out


def _to_float(v: Any, *, default: float | None = 0.0) -> float | None:
    """KRX 가 쉼표 박힌 문자열로 숫자 줄 때 안전 변환."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    if not s or s == "-":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


# ─── 통합 entry point ────────────────────────────────────────


PeriodKey = Literal["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"]

_PERIOD_DAYS: dict[str, int] = {
    "1M": 30, "3M": 92, "6M": 183,
    "1Y": 365, "3Y": 1095, "5Y": 1826, "10Y": 3650,
}


def period_to_dates(period: str, anchor: date | None = None) -> tuple[date, date]:
    """``"3M"`` / ``"1Y"`` → ``(start, end)`` 날짜.

    anchor 없으면 오늘. 사건 보고서면 사건 발생일 전달.
    """
    end = anchor or date.today()
    days = _PERIOD_DAYS.get((period or "3M").upper(), 92)
    start = end - timedelta(days=days)
    return start, end


async def fetch_market_series(
    instrument: str,
    period: str = "3M",
    config: Any | None = None,
    *,
    anchor_date: date | None = None,
) -> MarketSeries:
    """단일 instrument → MarketSeries.

    Args:
        instrument: "코스피" / "삼성전자" / "DXY" / "국고 10년" 등.
        period: "1M" / "3M" / "6M" / "1Y" / "3Y" / "5Y" / "10Y".
        config: src.config.Config (FRED_API_KEY / ECOS_API_KEY 보유).
        anchor_date: 끝 날짜 (default 오늘). 사건 보고서면 사건일.

    Returns:
        MarketSeries — ``data`` 가 비어있을 수 있음 (key 없거나 fetch 실패).
        호출자는 ``len(series.data) > 0`` 으로 분기.
    """
    spec = resolve_instrument(instrument)
    if not spec:
        logger.warning("[market_fetcher] 미등록 instrument: %r", instrument)
        return MarketSeries(instrument=instrument)

    start, end = period_to_dates(period, anchor_date)
    fred_key = getattr(config, "fred_api_key", "") if config else ""
    ecos_key = getattr(config, "ecos_api_key", "") if config else ""
    krx_key = getattr(config, "krx_api_key", "") if config else ""

    fetcher: FREDFetcher | ECOSFetcher | KRXFetcher
    if spec.source == "FRED":
        fetcher = FREDFetcher(fred_key)
    elif spec.source == "ECOS":
        fetcher = ECOSFetcher(ecos_key)
    elif spec.source == "KRX":
        fetcher = KRXFetcher(krx_key)
    else:
        return MarketSeries(
            instrument=spec.name, source=spec.source, code=spec.code,
            unit=spec.unit, chart_type=spec.chart_type,
        )

    data = await fetcher.fetch(spec.code, start, end)
    return MarketSeries(
        instrument=spec.name,
        source=spec.source,
        code=spec.code,
        unit=spec.unit,
        chart_type=spec.chart_type,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        data=data,
    )


async def fetch_many(
    instruments: list[str],
    period: str = "3M",
    config: Any | None = None,
    *,
    anchor_date: date | None = None,
) -> list[MarketSeries]:
    """병렬 fetch. 일부 실패해도 나머지 진행 — 실패한 series 는 ``data=[]``."""
    if not instruments:
        return []
    tasks = [
        fetch_market_series(inst, period, config, anchor_date=anchor_date)
        for inst in instruments
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[MarketSeries] = []
    for r, inst in zip(results, instruments):
        if isinstance(r, Exception):
            logger.warning("[market_fetcher] %s gather error: %s", inst, r)
            out.append(MarketSeries(instrument=inst))
        else:
            out.append(r)
    return out


__all__ = [
    "InstrumentSpec",
    "INSTRUMENT_REGISTRY",
    "OHLCBar",
    "MarketSeries",
    "FREDFetcher",
    "ECOSFetcher",
    "KRXFetcher",
    "resolve_instrument",
    "period_to_dates",
    "fetch_market_series",
    "fetch_many",
]
