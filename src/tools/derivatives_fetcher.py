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
from src.tools.krx_client import post_json_rows, warmup

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
    options: list[OptionQuote] = []
    if front and t:
        for o in parsed:
            if o["expiry"] != front:
                continue
            s = o["underlying"]
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
    spot = snap.futures.spot if snap.futures else None
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

    # 관심 콜·풋: OI 우선, 동률이면 거래량. 그릭 있는 것만.
    def _rank(o: OptionQuote) -> tuple[float, float]:
        return (o.oi or 0.0, o.volume or 0.0)

    snap.notable_calls = sorted(
        [o for o in calls if o.greeks is not None], key=_rank, reverse=True,
    )[:notable_n]
    snap.notable_puts = sorted(
        [o for o in puts if o.greeks is not None], key=_rank, reverse=True,
    )[:notable_n]

    snap.key_figures = _build_key_figures(snap)
    return snap


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
            "label": "옵션 최대고통(max pain) 행사가",
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
async def _post_rows(session, bld: str, params: dict) -> list[dict]:
    return await post_json_rows(session, bld, params)


async def _fetch_vkospi(session, trd_dd: str) -> float | None:
    """전체지수 시세에서 VKOSPI 종가 스캔(best-effort)."""
    try:
        rows = await _post_rows(session, BLD_INDEX_PRICES, {
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
    import aiohttp

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
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await warmup(session)  # KRX 세션 쿠키 확보 (없으면 getJsonData 400)
            results = await asyncio.gather(
                _post_rows(session, BLD_DERIV_PRICES, {
                    "locale": "ko_KR", "prodId": PROD_KOSPI200_FUT,
                    "trdDd": trd_dd, "mktTpCd": "T", "rghtTpCd": "T",
                    "share": "1", "money": "1",
                }),
                _post_rows(session, BLD_DERIV_PRICES, {
                    "locale": "ko_KR", "prodId": PROD_KOSPI200_OPT,
                    "trdDd": trd_dd, "mktTpCd": "T", "rghtTpCd": "T",
                    "share": "1", "money": "1",
                }),
                _fetch_vkospi(session, trd_dd),
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
    logger.info(
        "[derivatives] %s — futures=%s options=%d(front=%s) vkospi=%s pcr_vol=%s maxpain=%s kf=%d warn=%d",
        as_of, "ok" if snap.futures else "none", len(snap.options),
        snap.front_expiry, snap.vkospi, snap.pcr_volume, snap.max_pain,
        len(snap.key_figures), len(snap.warnings),
    )
    return snap


# ──────────────────────────────────────────────────────────────────────────
# VM 검증용 CLI — python -m src.tools.derivatives_fetcher [YYYYMMDD]
# ──────────────────────────────────────────────────────────────────────────
def _main() -> None:  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO)
    anchor = date.today()
    if len(sys.argv) > 1:
        try:
            anchor = datetime.strptime(sys.argv[1], "%Y%m%d").date()
        except ValueError:
            print("usage: python -m src.tools.derivatives_fetcher [YYYYMMDD]")
            return
    snap = asyncio.run(fetch_kr_derivatives_snapshot(anchor_date=anchor))
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
