"""KOSPI200 지수 선물·옵션 데이터 수집 + 그릭 산출 — v7.9.0.

장마감 브리핑(`scheduler/market_briefing.py`)의 *파생 데스크* 섹션이 실제 수치를
다룰 수 있게, KRX 정보데이터시스템(data.krx.co.kr) 공개 JSON 엔드포인트에서
KOSPI200 선물·옵션 전종목 시세를 받아 다음을 *결정적으로* 산출한다.

- 선물: 최근월물 종가·등락·미결제약정(OI)·거래량 + 현물(KOSPI200)과의 베이시스.
- 옵션 체인: 행사가별 콜/풋 프리미엄·OI·거래량 → 종가에서 **내재변동성(IV) 역산**
  → **그릭(델타/감마/세타/베가/로) 계산** (`src/tools/greeks.py`). 풋/콜 비율(거래량·OI),
  최대고통(max pain), 관심 콜·풋 행사가(OI/거래량 상위, ATM).

설계 원칙 (market_fetcher / image_fetcher 와 동일 graceful degrade):
- 네트워크·파싱 실패는 *조용히* 빈 snapshot + warning. 보고서 흐름은 절대 안 막음.
- 외부 의존: aiohttp(이미 사용) + stdlib + greeks(자체). pykrx 불요(엔드포인트 직접 POST).
- ``build_snapshot`` 은 *순수 함수* (raw rows → snapshot) 라 네트워크 없이 단위 테스트.
- 결과는 composer 가 이미 소비하는 ``key_figures`` 형태({label,value,context})로도
  내보내, orchestrator 가 ContextAnalysis.key_figures 에 병합 → 본문에 실수치 노출.

⚠️ KRX 엔드포인트(bld/prodId/컬럼명)는 pykrx 1.2.8 의 검증된 코드에서 가져왔으나,
샌드박스에서는 data.krx.co.kr 이 egress 정책으로 403 이라 *실연동은 VM 에서 검증* 한다.
VM 검증: ``python -m src.tools.derivatives_fetcher`` (오늘자 snapshot 출력).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from src.tools.greeks import (
    Greeks,
    black_scholes_greeks,
    implied_vol,
    max_pain,
    put_call_ratio,
)
from src.tools.krx_client import post_json_rows

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# pykrx 1.2.8 검증 — 파생 전종목 시세 + 파생상품 prodId.
BLD_DERIV_PRICES = "dbms/MDC/STAT/standard/MDCSTAT12501"
BLD_INDEX_PRICES = "dbms/MDC/STAT/standard/MDCSTAT00101"
PROD_KOSPI200_FUT = "KRDRVFUK2I"
PROD_KOSPI200_OPT = "KRDRVOPK2I"

DEFAULT_RISK_FREE = 0.03  # 연 3% (단기 국고채 근사 — 그릭 영향 작음, config 로 override)

# ISU_NM 예: "코스피200 C 202506 320.0" / "코스피200 P 202506 322.5 (주간)"
_OPT_NAME_RE = re.compile(r"\b([CP])\b\s+(\d{6})\s+([\d,]+(?:\.\d+)?)")


# ──────────────────────────────────────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FuturesQuote:
    name: str
    close: float | None
    change: float | None
    pct: float | None
    oi: float | None
    volume: float | None
    spot: float | None       # KOSPI200 현물
    basis: float | None      # close - spot


@dataclass(frozen=True)
class OptionQuote:
    option_type: str         # "call" | "put"
    strike: float
    expiry: str              # YYYYMM
    premium: float | None
    oi: float | None
    volume: float | None
    underlying: float | None
    greeks: Greeks | None    # iv 포함 (종가에서 역산)


@dataclass
class DerivativesSnapshot:
    as_of: str
    futures: FuturesQuote | None = None
    options: list[OptionQuote] = field(default_factory=list)
    front_expiry: str | None = None
    vkospi: float | None = None
    pcr_volume: float | None = None
    pcr_oi: float | None = None
    max_pain: float | None = None
    notable_calls: list[OptionQuote] = field(default_factory=list)
    notable_puts: list[OptionQuote] = field(default_factory=list)
    atm_iv: float | None = None
    key_figures: list[dict] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.futures or self.options or self.vkospi is not None)


# ──────────────────────────────────────────────────────────────────────────
# 파싱 헬퍼 (순수 — 테스트 대상)
# ──────────────────────────────────────────────────────────────────────────
def _f(v: object) -> float | None:
    """KRX 셀('1,234.5' / '-' / '') → float|None."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _second_thursday(year: int, month: int) -> date:
    """KOSPI200 월물 만기일 = 둘째 목요일."""
    d = date(year, month, 1)
    first_thu = 1 + (3 - d.weekday()) % 7  # Thursday=3
    return date(year, month, first_thu + 7)


def _expiry_T(yyyymm: str, anchor: date, *, floor_days: float = 0.5) -> float | None:
    """YYYYMM 만기 → 잔존만기(연). 만기 지났으면 None."""
    try:
        y, m = int(yyyymm[:4]), int(yyyymm[4:6])
        exp = _second_thursday(y, m)
    except (ValueError, IndexError):
        return None
    days = (exp - anchor).days
    if days < 0:
        return None
    return max(days, floor_days) / 365.0


def parse_futures(rows: list[dict]) -> FuturesQuote | None:
    """파생 전종목 시세(선물) rows → 최근월물 FuturesQuote.

    스프레드(SP)·만기물 제외, 거래량 있는 첫 단일물(F)을 최근월물로 본다.
    """
    best = None
    for r in rows:
        name = str(r.get("ISU_NM", ""))
        if " SP " in name or "SP " in name.split("코스피200")[-1][:4]:
            continue
        if " F " not in name and not name.replace(" ", "").find("F2") >= 0:
            # 단일 선물물만 (이름에 ' F ' 포함). 관대하게.
            if " F " not in f" {name} ":
                continue
        vol = _f(r.get("ACC_TRDVOL"))
        close = _f(r.get("TDD_CLSPRC"))
        if close is None:
            continue
        # 최근월물 = 거래량 최대 단일물.
        score = vol or 0.0
        if best is None or score > best[0]:
            best = (score, r)
    if best is None:
        return None
    r = best[1]
    close = _f(r.get("TDD_CLSPRC"))
    change = _f(r.get("CMPPREVDD_PRC"))
    spot = _f(r.get("SPOT_PRC"))
    prev = (close - change) if (close is not None and change is not None) else None
    pct = (change / prev * 100.0) if (change is not None and prev) else None
    basis = (close - spot) if (close is not None and spot is not None) else None
    return FuturesQuote(
        name=str(r.get("ISU_NM", "코스피200 선물")).strip(),
        close=close, change=change, pct=pct,
        oi=_f(r.get("ACC_OPNINT_QTY")), volume=_f(r.get("ACC_TRDVOL")),
        spot=spot, basis=basis,
    )


def parse_option_rows(rows: list[dict]) -> list[dict]:
    """파생 전종목 시세(옵션) rows → [{option_type,strike,expiry,premium,oi,volume,underlying}]."""
    out: list[dict] = []
    for r in rows:
        name = str(r.get("ISU_NM", ""))
        m = _OPT_NAME_RE.search(name)
        if not m:
            continue
        cp, yyyymm, strike_s = m.group(1), m.group(2), m.group(3)
        strike = _f(strike_s)
        if strike is None:
            continue
        out.append({
            "option_type": "call" if cp == "C" else "put",
            "strike": strike,
            "expiry": yyyymm,
            "premium": _f(r.get("TDD_CLSPRC")),
            "oi": _f(r.get("ACC_OPNINT_QTY")),
            "volume": _f(r.get("ACC_TRDVOL")),
            "underlying": _f(r.get("SPOT_PRC")),
        })
    return out


def _select_front_expiry(parsed: list[dict]) -> str | None:
    """거래량 합이 가장 큰 만기(YYYYMM)를 활성 최근월물로."""
    by_exp: dict[str, float] = {}
    for o in parsed:
        by_exp[o["expiry"]] = by_exp.get(o["expiry"], 0.0) + (o["volume"] or 0.0)
    if not by_exp:
        return None
    return max(by_exp.items(), key=lambda kv: kv[1])[0]


# ──────────────────────────────────────────────────────────────────────────
# Snapshot 조립 (순수 — 테스트 대상)
# ──────────────────────────────────────────────────────────────────────────
def _fmt(v: float | None, nd: int = 2, suffix: str = "") -> str:
    if v is None:
        return "확인되지 않음"
    return f"{v:,.{nd}f}{suffix}"


def build_snapshot(
    *,
    as_of: str,
    anchor: date,
    futures_rows: list[dict] | None,
    option_rows: list[dict] | None,
    vkospi: float | None = None,
    risk_free: float = DEFAULT_RISK_FREE,
    notable_n: int = 3,
    notable_band: float = 0.15,
) -> DerivativesSnapshot:
    """raw KRX rows → DerivativesSnapshot (IV·그릭·PCR·max pain·관심 행사가·key_figures).

    네트워크 없이 호출 가능 — fetch 와 분리해 테스트한다.
    """
    snap = DerivativesSnapshot(as_of=as_of, vkospi=vkospi)
    snap.futures = parse_futures(futures_rows or [])

    parsed = parse_option_rows(option_rows or [])
    front = _select_front_expiry(parsed)
    snap.front_expiry = front

    t = _expiry_T(front, anchor) if front else None
    # 기초자산(KOSPI200 현물). 옵션 행에 SPOT_PRC 가 없으면(KRX 옵션 시세 미제공)
    # 선물 행의 현물가로 폴백 — 안 그러면 전 행 IV/그릭이 계산 안 됨(VM 실측 회귀).
    fut_spot = snap.futures.spot if snap.futures else None
    chain_spot = next((o["underlying"] for o in parsed if o.get("underlying")), None) or fut_spot
    options: list[OptionQuote] = []
    if front and t:
        for o in parsed:
            if o["expiry"] != front:
                continue
            s = o["underlying"] or chain_spot
            k = o["strike"]
            prem = o["premium"]
            greeks = None
            if s and prem and prem > 0:
                iv = implied_vol(prem, s, k, t, risk_free, o["option_type"])  # type: ignore[arg-type]
                if iv is not None:
                    greeks = black_scholes_greeks(
                        s, k, t, risk_free, iv, o["option_type"], 0.0,  # type: ignore[arg-type]
                    )
            options.append(OptionQuote(
                option_type=o["option_type"], strike=k, expiry=front,
                premium=prem, oi=o["oi"], volume=o["volume"],
                underlying=s, greeks=greeks,
            ))
    snap.options = options

    # PCR (거래량·OI), max pain — 활성 만기 기준.
    calls = [o for o in options if o.option_type == "call"]
    puts = [o for o in options if o.option_type == "put"]
    snap.pcr_volume = put_call_ratio(
        sum(o.volume or 0 for o in puts), sum(o.volume or 0 for o in calls),
    )
    snap.pcr_oi = put_call_ratio(
        sum(o.oi or 0 for o in puts), sum(o.oi or 0 for o in calls),
    )
    # max pain: 행사가별 (k, call_oi, put_oi)
    strike_oi: dict[float, list[float]] = {}
    for o in options:
        cp = strike_oi.setdefault(o.strike, [0.0, 0.0])
        if o.option_type == "call":
            cp[0] += o.oi or 0.0
        else:
            cp[1] += o.oi or 0.0
    snap.max_pain = max_pain([(k, v[0], v[1]) for k, v in strike_oi.items()])

    # ATM IV — 현물에 가장 가까운 행사가의 콜/풋 IV 평균.
    spot = chain_spot
    if spot is None and options:
        spot = next((o.underlying for o in options if o.underlying), None)
    if spot and options:
        atm_strike = min({o.strike for o in options}, key=lambda k: abs(k - spot))
        ivs = [
            o.greeks.iv for o in options
            if o.strike == atm_strike and o.greeks is not None
        ]
        if ivs:
            snap.atm_iv = sum(ivs) / len(ivs)

    # 관심 콜·풋: 현물 ±notable_band 밴드 안(의사결정 관련 행사가)에서 OI 우선,
    # 동률이면 거래량. 그릭 있는 것만. 딥OTM 꼬리(미결제만 큰 복권)는 제외해도
    # 스큐·PCR·max pain 엔 계속 반영됨. 밴드 안 후보가 부족하면 전체로 완화.
    def _rank(o: OptionQuote) -> tuple[float, float]:
        return (o.oi or 0.0, o.volume or 0.0)

    def _in_band(o: OptionQuote) -> bool:
        if not spot:
            return True
        return spot * (1.0 - notable_band) <= o.strike <= spot * (1.0 + notable_band)

    def _pick(side: list[OptionQuote]) -> list[OptionQuote]:
        graded = [o for o in side if o.greeks is not None]
        banded = [o for o in graded if _in_band(o)]
        pool = banded if len(banded) >= notable_n else graded
        return sorted(pool, key=_rank, reverse=True)[:notable_n]

    snap.notable_calls = _pick(calls)
    snap.notable_puts = _pick(puts)

    snap.key_figures = _build_key_figures(snap)
    snap.charts = build_derivatives_charts(snap)
    return snap


def build_derivatives_charts(snap: "DerivativesSnapshot") -> list[dict]:
    """snapshot → 옵션 데스크 직관 차트 (deterministic, 장마감 브리핑 전용, v7.9.9).

    서술 위주이던 '옵션 시장이 보낸 신호' 섹션에 시인성 있는 비주얼을 결정적으로
    주입(사용자 요청). composer 에 의존하지 않아 *모든* 향후 브리핑에 반영된다.
      ① IV 스큐 scatter — 행사가별 내재변동성 + ATM 기준선(hline) + 하단 설명.
      ② 풋/콜 비율 bullet — 중립(1.0) 대비 어느 쪽으로 기울었는지.
      ③ 행사가별 미결제(OI) 발산 막대 — 콜(우)/풋(좌), 매물벽·max pain 위치 직관.
    데이터 부족 항목은 해당 차트만 생략(graceful).
    """
    charts: list[dict] = []

    # ① IV 스큐 곡선 — 전체 옵션 체인의 행사가별 IV 를 풋(파랑)/콜(빨강) 두 곡선으로
    #    연결(스큐 트렌드 시각화). 현물 ±28% 밴드(스큐 꼬리 포함 — v7.9.11 사용자
    #    피드백으로 ±18%→±28% 확대) + 비현실 IV(역산 실패 꼬리) 제외. 각 점에 date.
    spot = snap.futures.spot if snap.futures else None
    sk: list[dict] = []
    seen: set[tuple[str, float]] = set()
    for o in (snap.options or []):
        if o.greeks is None or o.greeks.iv is None or not o.strike:
            continue
        iv_pct = o.greeks.iv * 100.0
        if not (3.0 <= iv_pct <= 200.0):
            continue
        if spot and not (spot * 0.72 <= o.strike <= spot * 1.28):
            continue
        key = (o.option_type, float(o.strike))
        if key in seen:
            continue
        seen.add(key)
        sk.append({
            "strike": float(o.strike),
            "iv": round(iv_pct, 1),
            "type": o.option_type,  # 'put' | 'call'
            "date": snap.as_of,
        })
    distinct_strikes = len({d["strike"] for d in sk})
    if len(sk) >= 4 and distinct_strikes >= 3:
        chart: dict = {
            "type": "iv_skew",
            "title": f"행사가별 내재변동성 (KOSPI200 {snap.front_expiry or ''}물)".strip(),
            "subtitle": "풋(파랑)·콜(빨강)을 행사가 순으로 이은 변동성 스큐 곡선",
            "x_label": "행사가",
            "data": sorted(sk, key=lambda d: d["strike"]),
            "note": (
                "내재변동성(IV)은 옵션 가격에 녹아든 '앞으로 이만큼 출렁일 것'이라는 "
                "시장의 예상치다. 점선 가로 기준선은 등가격(ATM) 옵션의 IV — 모든 행사가가 "
                "같은 변동성으로 거래된다고 가정했을 때의 수평선이다. 실제로는 하락을 "
                "방어하는 외가격 풋(왼쪽 파란 곡선)이 기준선 위로 솟는다(스큐). 풋 곡선이 "
                "콜보다 높다는 건 시장이 상승보다 하락 꼬리를 더 비싸게 사고 있다는 신호다."
            ),
            "source": f"KRX 종가에서 산출 / {snap.as_of}",
        }
        if snap.atm_iv is not None:
            chart["atm_iv"] = round(snap.atm_iv * 100.0, 1)
        charts.append(chart)

    # ② 풋/콜 비율 bullet — 중립 1.0 대비
    pcr = snap.pcr_volume if snap.pcr_volume is not None else snap.pcr_oi
    if pcr is not None and pcr > 0:
        charts.append({
            "type": "bullet",
            "title": "풋/콜 비율 — 중립(1.0) 대비",
            "data": [{
                "label": "풋콜비율(거래량)",
                "value": round(float(pcr), 2),
                "target": 1.0,
                "ranges": [1.0, max(2.0, round(float(pcr) * 0.6, 1)), round(float(pcr) * 1.05, 1)],
            }],
            "note": (
                "풋 거래량을 콜 거래량으로 나눈 값. 세로 표식(1.0)이 중립선이다. "
                "1보다 크면 하방 헤지·약세 베팅이 우세하다는 뜻이지만, 극단적으로 높으면 "
                "오히려 단기 바닥을 가리키는 역지표로도 읽힌다."
            ),
            "source": f"KRX 정보데이터시스템 / {snap.as_of} (활성 만기 {snap.front_expiry or '확인되지 않음'})",
        })

    # ③ 행사가별 미결제약정(OI) 발산 막대 — 콜(우) / 풋(좌)
    strike_oi: dict[float, list[float]] = {}
    for o in (snap.options or []):
        if not o.strike or o.oi is None or o.oi <= 0:
            continue
        cell = strike_oi.setdefault(float(o.strike), [0.0, 0.0])
        if o.option_type == "call":
            cell[0] += float(o.oi)
        else:
            cell[1] += float(o.oi)
    rows = [
        {"label": f"{k:g}", "pos": v[0], "neg": v[1], "_k": k}
        for k, v in strike_oi.items() if (v[0] > 0 or v[1] > 0)
    ]
    if len(rows) >= 2:
        # OI 합 상위 ~8개 → 행사가 오름차순(위→아래) 정렬.
        rows.sort(key=lambda r: r["pos"] + r["neg"], reverse=True)
        rows = rows[:8]
        rows.sort(key=lambda r: r["_k"], reverse=True)
        for r in rows:
            r.pop("_k", None)
        charts.append({
            "type": "diverging_bar",
            "title": "행사가별 미결제약정 — 콜(우) vs 풋(좌)",
            "data": rows,
            "note": (
                "행사가마다 청산되지 않고 남은 계약 수(미결제약정). 막대가 두꺼운 "
                "행사가는 매물벽으로 작용해 만기 부근 지수를 끌어당기는 자석(max pain)이 "
                "되기 쉽다. 풋이 쌓인 아래쪽은 지지, 콜이 쌓인 위쪽은 저항으로 읽는다."
            ),
            "source": f"KRX 정보데이터시스템 / {snap.as_of} (활성 만기 {snap.front_expiry or ''})".strip(),
        })

    # ④ 선물 베이시스 한 줄 지표 — 0 중심, 부호별 색(콘탱고=양/백워데이션=음).
    fut = snap.futures
    if fut and fut.basis is not None:
        charts.append({
            "type": "indicator",
            "title": "선물 베이시스 — 콘탱고/백워데이션",
            "data": [{
                "label": "선물 - 현물",
                "value": round(float(fut.basis), 2),
                "unit": "p",
                "pos_label": "콘탱고",
                "neg_label": "백워데이션",
            }],
            "note": (
                "선물 가격에서 현물(KOSPI200)을 뺀 값. 0보다 크면 콘탱고(정상 — 시장이 "
                "위험을 무난히 가격에 반영), 0보다 작으면 백워데이션(수급 왜곡·하락 베팅 "
                "신호). 괴리가 크면 차익거래 프로그램 매물이 현물 수급을 흔들 수 있다."
            ),
            "source": f"KRX / {snap.as_of} (현물 {_fmt(fut.spot)})",
        })

    return charts


def _greeks_ctx(g: Greeks) -> str:
    return (
        f"델타 {g.delta:+.3f} · 감마 {g.gamma:.4f} · 세타 {g.theta:+.3f}/일 · "
        f"베가 {g.vega:.3f} · 로 {g.rho:+.3f}"
    )


def _build_key_figures(snap: DerivativesSnapshot) -> list[dict]:
    """snapshot → composer 가 소비하는 key_figures({label,value,context}) 목록.

    출처·기준 시점을 context 에 명시(WRITE-AP-22 시점 규율). IV·그릭은 종가 역산임을 표기.
    """
    src = f"(KRX 정보데이터시스템, {snap.as_of} 종가 기준)"
    src_calc = f"(KRX 종가에서 산출, {snap.as_of})"
    kfs: list[dict] = []

    fut = snap.futures
    if fut and fut.close is not None:
        chg = ""
        if fut.change is not None:
            chg = f" ({fut.change:+.2f}"
            chg += f", {fut.pct:+.2f}%)" if fut.pct is not None else ")"
        ctx_bits = []
        if fut.basis is not None:
            cb = "콘탱고" if fut.basis >= 0 else "백워데이션"
            ctx_bits.append(f"베이시스 {fut.basis:+.2f} ({cb}, 현물 {_fmt(fut.spot)})")
        if fut.oi is not None:
            ctx_bits.append(f"미결제약정 {_fmt(fut.oi, 0)}계약")
        if fut.volume is not None:
            ctx_bits.append(f"거래량 {_fmt(fut.volume, 0)}계약")
        kfs.append({
            "label": f"KOSPI200 선물 {fut.name} 종가",
            "value": f"{_fmt(fut.close)}{chg}",
            "context": " · ".join(ctx_bits) + f" {src}",
        })

    if snap.vkospi is not None:
        kfs.append({
            "label": "VKOSPI (변동성지수)",
            "value": _fmt(snap.vkospi),
            "context": f"한국판 공포지수 — 상승=헤지수요·변동성 확대 기대 {src}",
        })

    if snap.pcr_volume is not None or snap.pcr_oi is not None:
        kfs.append({
            "label": "풋/콜 비율",
            "value": (
                f"거래량 {_fmt(snap.pcr_volume)} · 미결제 {_fmt(snap.pcr_oi)}"
            ),
            "context": (
                f"높을수록 하방 헤지·약세 심리(과도하면 역지표). 활성 만기 {snap.front_expiry or '확인되지 않음'} 기준 {src}"
            ),
        })

    if snap.max_pain is not None:
        kfs.append({
            "label": "옵션 max pain 행사가",
            "value": _fmt(snap.max_pain),
            "context": (
                f"만기 부근 지수를 끌어당기는 자석 레벨 추정(행사가별 미결제 기반) {src_calc}"
            ),
        })

    if snap.atm_iv is not None:
        kfs.append({
            "label": "ATM 내재변동성(IV)",
            "value": f"{snap.atm_iv * 100:,.1f}%",
            "context": f"등가격 옵션 종가에서 역산한 내재변동성 {src_calc}",
        })

    for tag, items in (("콜", snap.notable_calls), ("풋", snap.notable_puts)):
        for o in items:
            if o.greeks is None:
                continue
            kfs.append({
                "label": f"관심 {tag}옵션 {o.strike:g} ({o.expiry})",
                "value": (
                    f"프리미엄 {_fmt(o.premium)} · IV {o.greeks.iv * 100:,.1f}%"
                ),
                "context": (
                    f"{_greeks_ctx(o.greeks)} · 미결제 {_fmt(o.oi, 0)} · "
                    f"거래량 {_fmt(o.volume, 0)} {src_calc}"
                ),
            })

    return kfs


# ──────────────────────────────────────────────────────────────────────────
# 네트워크 (best-effort — VM 검증)
# ──────────────────────────────────────────────────────────────────────────
async def _fetch_vkospi(config, trd_dd: str) -> float | None:
    """전체지수 시세에서 VKOSPI 종가 스캔(best-effort)."""
    try:
        rows = await post_json_rows(config, BLD_INDEX_PRICES, {
            "locale": "ko_KR", "idxIndMidclssCd": "02", "trdDd": trd_dd,
            "share": "1", "money": "1",
        })
    except Exception:
        return None
    for r in rows:
        nm = str(r.get("IDX_NM", "")) + str(r.get("IDX_IND_NM", ""))
        if "변동성" in nm or "VKOSPI" in nm.upper():
            return _f(r.get("CLSPRC_IDX") or r.get("TDD_CLSPRC") or r.get("CLSPRC"))
    return None


def augment_skew_history(
    snap: "DerivativesSnapshot", *, config=None, n_days: int = 10
) -> None:
    """오늘 IV 스큐를 캐시에 저장하고, 지난 n_days 영업일 스큐를 iv_skew 차트에 병합.

    차트의 ``data`` 를 다일자 점(각 점에 ``date``)으로 교체 → 렌더러가 나이순 페이드
    오버레이로 그린다. 캐시 없거나 단일일이면 오늘 점만 남아 기존 단일 곡선과 동일
    (graceful). front_expiry 없으면 no-op.
    """
    if not snap.front_expiry or not snap.charts:
        return
    skew_chart = next((c for c in snap.charts if c.get("type") == "iv_skew"), None)
    if skew_chart is None:
        return
    today_pts = [
        {"strike": d["strike"], "iv": d["iv"], "type": d["type"]}
        for d in (skew_chart.get("data") or [])
        if "strike" in d and "iv" in d and "type" in d
    ]
    if not today_pts:
        return
    from src.tools.skew_cache import store_skew, recent_skew
    path = getattr(config, "skew_cache_path", "data/iv_skew.sqlite")
    store_skew(path, snap.as_of, snap.front_expiry, today_pts)
    hist = recent_skew(path, snap.front_expiry, n_days, snap.as_of)
    if len(hist) >= len(today_pts):  # 캐시 읽기 성공 (최소 오늘치 포함)
        skew_chart["data"] = hist
        n_dates = len({h["date"] for h in hist})
        if n_dates > 1:
            skew_chart["subtitle"] = (
                f"풋(파랑)·콜(빨강) 스큐 곡선 — 진한 곡선이 오늘, 옅을수록 과거 (최근 {n_dates}영업일)"
            )


async def fetch_kr_derivatives_snapshot(
    *,
    anchor_date: date | None = None,
    config: "Config | None" = None,
    risk_free: float | None = None,
    timeout_s: float = 20.0,
) -> DerivativesSnapshot:
    """KRX 에서 KOSPI200 선물·옵션 전종목 시세를 받아 snapshot 조립.

    실패(네트워크/파싱/엔드포인트)는 빈 snapshot + warning — 보고서 흐름 무영향.
    """
    anchor = anchor_date or date.today()
    trd_dd = anchor.strftime("%Y%m%d")
    as_of = anchor.isoformat()
    r = (
        risk_free
        if risk_free is not None
        else float(getattr(config, "derivatives_risk_free", DEFAULT_RISK_FREE) or DEFAULT_RISK_FREE)
    )

    fut_rows: list[dict] = []
    opt_rows: list[dict] = []
    vkospi: float | None = None
    warnings: list[str] = []

    try:
        # KRX 인증 세션으로 직접 POST (krx_client 가 로그인·세션 관리, 요청은 to_thread).
        results = await asyncio.gather(
            post_json_rows(config, BLD_DERIV_PRICES, {
                "locale": "ko_KR", "prodId": PROD_KOSPI200_FUT,
                "trdDd": trd_dd, "mktTpCd": "T", "rghtTpCd": "T",
                "share": "1", "money": "1",
            }),
            post_json_rows(config, BLD_DERIV_PRICES, {
                "locale": "ko_KR", "prodId": PROD_KOSPI200_OPT,
                "trdDd": trd_dd, "mktTpCd": "T", "rghtTpCd": "T",
                "share": "1", "money": "1",
            }),
            _fetch_vkospi(config, trd_dd),
            return_exceptions=True,
        )
        fut_res, opt_res, vk_res = results
        if isinstance(fut_res, list):
            fut_rows = fut_res
        else:
            warnings.append(f"futures fetch 실패: {fut_res}")
        if isinstance(opt_res, list):
            opt_rows = opt_res
        else:
            warnings.append(f"options fetch 실패: {opt_res}")
        if isinstance(vk_res, (int, float)):
            vkospi = float(vk_res)
    except Exception as e:  # pragma: no cover — 네트워크 차단 환경
        logger.warning("[derivatives] KRX fetch 실패 (graceful skip): %s", e)
        snap = DerivativesSnapshot(as_of=as_of)
        snap.warnings = [f"fetch 예외: {e}"]
        return snap

    snap = build_snapshot(
        as_of=as_of, anchor=anchor,
        futures_rows=fut_rows, option_rows=opt_rows,
        vkospi=vkospi, risk_free=r,
    )
    snap.warnings = warnings
    # v7.9.11 — 오늘 스큐 캐시 저장 + 지난 N영업일 오버레이 (graceful).
    try:
        augment_skew_history(snap, config=config)
    except Exception as e:  # pragma: no cover
        logger.warning("[derivatives] skew history augment skipped: %s", e)
    logger.info(
        "[derivatives] %s — futures=%s options=%d(front=%s) vkospi=%s pcr_vol=%s maxpain=%s kf=%d warn=%d",
        as_of, "ok" if snap.futures else "none", len(snap.options),
        snap.front_expiry, snap.vkospi, snap.pcr_volume, snap.max_pain,
        len(snap.key_figures), len(snap.warnings),
    )
    return snap


async def backfill_skew(*, days: int = 14, config=None) -> int:
    """지난 ``days`` 일을 거슬러 IV 스큐 캐시를 채운다 (영업일 ~10일 확보용, v7.9.11).

    날마다 fetch_kr_derivatives_snapshot 가 build → augment_skew_history 로 store 까지
    수행하므로, 여기선 날짜를 거슬러 호출만 한다. 주말/휴일·데이터 없는 날은 skip.
    """
    from datetime import timedelta
    stored = 0
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:  # 토/일 skip
            continue
        snap = await fetch_kr_derivatives_snapshot(anchor_date=d, config=config)
        skew = next((c for c in snap.charts if c.get("type") == "iv_skew"), None)
        if skew and snap.front_expiry:
            stored += 1
            print(f"  {d.isoformat()} — front={snap.front_expiry} pts={len(skew.get('data') or [])}")
    print(f"backfill_skew done — {stored} 영업일 적재")
    return stored


# ──────────────────────────────────────────────────────────────────────────
# VM 검증용 CLI — python -m src.tools.derivatives_fetcher [YYYYMMDD]
#                 python -m src.tools.derivatives_fetcher skew-backfill --days 14
# ──────────────────────────────────────────────────────────────────────────
def _main() -> None:  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO)
    try:
        from src.config import Config
        cfg = Config()
    except Exception as e:
        print(f"[warn] Config 로드 실패({e}) — KRX 로그인 없이 진행")
        cfg = None
    if len(sys.argv) > 1 and sys.argv[1] == "skew-backfill":
        days = 14
        if "--days" in sys.argv:
            try:
                days = int(sys.argv[sys.argv.index("--days") + 1])
            except (ValueError, IndexError):
                pass
        asyncio.run(backfill_skew(days=days, config=cfg))
        return
    anchor = date.today()
    if len(sys.argv) > 1:
        try:
            anchor = datetime.strptime(sys.argv[1], "%Y%m%d").date()
        except ValueError:
            print("usage: python -m src.tools.derivatives_fetcher [YYYYMMDD]")
            return
    snap = asyncio.run(fetch_kr_derivatives_snapshot(anchor_date=anchor, config=cfg))
    print(f"\n=== KOSPI200 파생 snapshot ({snap.as_of}) ===")
    print(f"has_data={snap.has_data}  warnings={snap.warnings}")
    if snap.futures:
        print("선물:", snap.futures)
    print(f"옵션 {len(snap.options)}건, 활성만기={snap.front_expiry}, "
          f"PCR(vol)={snap.pcr_volume}, PCR(oi)={snap.pcr_oi}, "
          f"maxpain={snap.max_pain}, atm_iv={snap.atm_iv}, vkospi={snap.vkospi}")
    print(f"\n--- key_figures ({len(snap.key_figures)}) ---")
    for kf in snap.key_figures:
        print(f"• {kf['label']}: {kf['value']}\n    {kf['context']}")


if __name__ == "__main__":  # pragma: no cover
    _main()
