"""시장 등락 종목 수(breadth) 수집 + 추세·상관 산출 — v7.9.0.

장마감 브리핑의 *시장 폭* 분석. 코스피/코스닥 전종목의 일별 등락 종목 수(상승/하락/
보합)와 하락 비율을 집계해, 지수가 소수 대형주로 올라도 *체감 시장* 이 약한지(좁은 장)
드러낸다. (사용자 제공 breadth 통합 지시서의 분석 내용을 agents_reviewer 아키텍처에
맞춰 네이티브 통합 — matplotlib PNG/별도 cron 대신 KRX 무로그인 fetch + d3 차트 + key_figures.)

데이터 출처: KRX 정보데이터시스템 전종목 시세(MDCSTAT01501, mktId=STK/KSQ). 등락은
FLUC_RT(등락률) 부호로 카운트 — pykrx 의 KRX_ID/PW 로그인 불요(derivatives_fetcher 와
동일한 무로그인 POST). 멱등 SQLite 캐시로 과거일을 재수집하지 않고 신규일만 append
(지시서 §0 '수집/표현 분리·멱등 append' 원칙).

설계: market_fetcher / derivatives_fetcher 와 동일 graceful degrade — 실패는 빈 snapshot
+ warning, 보고서 흐름 무영향. 순수 집계·요약 함수(count_breadth/summarize_market/
build_key_figures)는 네트워크 없이 단위 테스트.

⚠️ data.krx.co.kr 은 샌드박스에서 egress 403 → 실연동은 VM 검증.
  VM 검증: ``python -m src.tools.breadth_fetcher [YYYYMMDD]``
  최초 이력 적재: ``python -m src.tools.breadth_fetcher backfill --days 120``
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from src.tools.krx_client import post_json_rows

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

BLD_STOCK_PRICES = "dbms/MDC/STAT/standard/MDCSTAT01501"  # pykrx 검증 — 전종목 시세
MKT_ID = {"KOSPI": "STK", "KOSDAQ": "KSQ"}

DEFAULT_CACHE_PATH = "data/market_internals.sqlite"
DEFAULT_LOOKBACK = 20      # 브리핑 추세·차트용 영업일
DEFAULT_MAX_FETCH = 25     # 1회 실행 inline 백필 상한(레이턴시 보호)


# ──────────────────────────────────────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DailyBreadth:
    market: str
    date: str          # ISO YYYY-MM-DD
    up: int
    down: int
    flat: int
    total: int

    @property
    def down_ratio(self) -> float:
        return (self.down / self.total) if self.total else 0.0


@dataclass
class MarketBreadthView:
    market: str
    last: DailyBreadth
    dr_last: float           # 당일 하락비율 %
    dr_avg5: float
    dr_avg20: float
    trend: str               # '확대' | '완화'
    corr: float | None       # 하락비율 ↔ 향후 5일 지수수익률 상관
    series: list[DailyBreadth] = field(default_factory=list)


@dataclass
class BreadthSnapshot:
    as_of: str
    views: list[MarketBreadthView] = field(default_factory=list)
    key_figures: list[dict] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.views)


# ──────────────────────────────────────────────────────────────────────────
# 순수 집계·요약 (테스트 대상)
# ──────────────────────────────────────────────────────────────────────────
def _num(v: object) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def count_breadth(rows: list[dict], market: str, day: str) -> DailyBreadth | None:
    """전종목 시세 rows → 등락 종목 수. FLUC_RT(등락률) 부호 우선, CMPPREVDD_PRC 폴백.

    거래정지·가격 0 종목(TDD_CLSPRC<=0)은 제외. 유효 종목 0 이면 None(휴장 등).
    """
    up = down = flat = 0
    for r in rows:
        close = _num(r.get("TDD_CLSPRC"))
        if close is None or close <= 0:
            continue
        chg = _num(r.get("FLUC_RT"))
        if chg is None:
            chg = _num(r.get("CMPPREVDD_PRC"))
        if chg is None:
            continue
        if chg > 0:
            up += 1
        elif chg < 0:
            down += 1
        else:
            flat += 1
    total = up + down + flat
    if total == 0:
        return None
    return DailyBreadth(market=market, date=day, up=up, down=down, flat=flat, total=total)


def corr_lagged(
    series: list[DailyBreadth], index_closes: dict[str, float] | None,
    smooth: int = 5, lag: int = 5,
) -> float | None:
    """하락비율(평활) ↔ 향후 ``lag`` 영업일 지수수익률 상관.

    index_closes: {ISO date: close}. 표본 < 20 이면 None(지시서: 단정 금지).
    음수 = '하락비율↑ 이후 지수↓' 가설 지지.
    """
    if not index_closes or len(series) < smooth + lag + 20:
        return None
    s = sorted(series, key=lambda d: d.date)
    dates = [d.date for d in s]
    dr = [d.down_ratio for d in s]
    # 평활 (단순 이동평균)
    drs: list[float | None] = []
    for i in range(len(dr)):
        if i + 1 < smooth:
            drs.append(None)
        else:
            drs.append(sum(dr[i + 1 - smooth:i + 1]) / smooth)
    xs: list[float] = []
    ys: list[float] = []
    for i in range(len(s) - lag):
        d0, d5 = dates[i], dates[i + lag]
        c0, c5 = index_closes.get(d0), index_closes.get(d5)
        if drs[i] is not None and c0 and c5 and c0 > 0:
            xs.append(drs[i])  # type: ignore[arg-type]
            ys.append((c5 - c0) / c0)
    if len(xs) < 20:
        return None
    return _pearson(xs, ys)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def summarize_market(
    series: list[DailyBreadth], index_closes: dict[str, float] | None = None,
) -> MarketBreadthView | None:
    if not series:
        return None
    s = sorted(series, key=lambda d: d.date)
    last = s[-1]

    def _avg_dr(n: int) -> float:
        tail = s[-n:]
        return (sum(d.down_ratio for d in tail) / len(tail) * 100.0) if tail else 0.0

    dr_last = last.down_ratio * 100.0
    dr_avg5 = _avg_dr(5)
    dr_avg20 = _avg_dr(20)
    trend = "확대" if dr_avg5 > dr_avg20 else "완화"
    corr = corr_lagged(s, index_closes)
    return MarketBreadthView(
        market=last.market, last=last, dr_last=dr_last, dr_avg5=dr_avg5,
        dr_avg20=dr_avg20, trend=trend, corr=corr, series=s,
    )


def build_key_figures(views: list[MarketBreadthView], as_of: str) -> list[dict]:
    """breadth views → composer 가 소비하는 key_figures."""
    src = f"(KRX 정보데이터시스템 전종목 등락 집계, {as_of} 기준)"
    kfs: list[dict] = []
    for v in views:
        kfs.append({
            "label": f"{v.market} 등락 종목 수",
            "value": f"상승 {v.last.up} / 하락 {v.last.down} / 보합 {v.last.flat} (총 {v.last.total})",
            "context": (
                f"하락비율 당일 {v.dr_last:.1f}% · 5일 평균 {v.dr_avg5:.1f}% · "
                f"20일 평균 {v.dr_avg20:.1f}% → 하락 압력 {v.trend} 국면 {src}"
            ),
        })
        if v.corr is not None:
            verdict = (
                "음의 상관 — 하락비율 상승이 이후 지수 약세에 선행하는 단서"
                if v.corr < -0.1 else
                "뚜렷한 선행성 없음 — 이번 국면에선 breadth 선행성 약함"
            )
            kfs.append({
                "label": f"{v.market} 하락비율↔향후 지수 상관",
                "value": f"{v.corr:+.2f}",
                "context": (
                    f"하락비율(5일 평활) vs 향후 5영업일 지수수익률 상관. {verdict}. "
                    f"등락 종목 수는 대형주 지수와 괴리될 수 있어 단독 트리거로 보지 않음 {src}"
                ),
            })
    return kfs


def build_charts(views: list[MarketBreadthView], min_points: int = 5) -> list[dict]:
    """decline-ratio line 차트 (시장별). 포인트 부족하면 생략."""
    charts: list[dict] = []
    for v in views:
        pts = [
            {"x": d.date, "y": round(d.down_ratio * 100.0, 1)}
            for d in v.series
        ]
        if len(pts) < min_points:
            continue
        charts.append({
            "type": "line",
            "title": f"{v.market} 하락 종목 비율 (최근 {len(pts)}영업일)",
            "data": pts,
            "note": (
                "전종목 중 하락 종목 비율(%). 50% 위는 하락 우위(좁은 장). "
                "지수가 대형주로 올라도 이 비율이 높으면 체감 시장은 약함."
            ),
        })
    return charts


# ──────────────────────────────────────────────────────────────────────────
# SQLite 캐시 (멱등 append)
# ──────────────────────────────────────────────────────────────────────────
def _cache_connect(path: str) -> sqlite3.Connection | None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS breadth ("
            "market TEXT NOT NULL, date TEXT NOT NULL, "
            "up INTEGER, down INTEGER, flat INTEGER, total INTEGER, "
            "PRIMARY KEY (market, date))"
        )
        conn.commit()
        return conn
    except Exception as e:  # pragma: no cover
        logger.warning("[breadth] cache open 실패 (%s): %s", path, e)
        return None


def _cache_load(conn: sqlite3.Connection, market: str, start: str, end: str) -> list[DailyBreadth]:
    cur = conn.execute(
        "SELECT market,date,up,down,flat,total FROM breadth "
        "WHERE market=? AND date>=? AND date<=? ORDER BY date",
        (market, start, end),
    )
    return [DailyBreadth(*row) for row in cur.fetchall()]


def _cache_upsert(conn: sqlite3.Connection, db: DailyBreadth) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO breadth(market,date,up,down,flat,total) VALUES(?,?,?,?,?,?)",
        (db.market, db.date, db.up, db.down, db.flat, db.total),
    )


def _business_days(end: date, n_back: int) -> list[date]:
    """end 포함 직전 평일 n_back 개(역순 아님, 오름차순). 휴장은 fetch 단계서 걸러짐."""
    out: list[date] = []
    d = end
    while len(out) < n_back:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


# ──────────────────────────────────────────────────────────────────────────
# 네트워크 (best-effort — VM 검증)
# ──────────────────────────────────────────────────────────────────────────
async def _fetch_day(config, market: str, day: date) -> DailyBreadth | None:
    try:
        rows = await post_json_rows(config, BLD_STOCK_PRICES, {
            "mktId": MKT_ID[market], "trdDd": day.strftime("%Y%m%d"),
            "share": "1", "money": "1",
        })
    except Exception as e:
        logger.warning("[breadth] %s %s fetch 실패: %s", market, day, e)
        return None
    return count_breadth(rows, market, day.isoformat())


async def fetch_market_breadth_snapshot(
    *,
    anchor_date: date | None = None,
    config: "Config | None" = None,
    index_closes: dict[str, dict[str, float]] | None = None,
    lookback: int = DEFAULT_LOOKBACK,
    max_fetch: int = DEFAULT_MAX_FETCH,
) -> BreadthSnapshot:
    """코스피/코스닥 breadth snapshot. 캐시에 없는 신규 영업일만 bounded 수집.

    index_closes: {market: {ISO date: close}} (상관 분석용, 보통 context.time_series 에서).
    실패는 빈 snapshot + warning — 보고서 흐름 무영향.
    """
    anchor = anchor_date or date.today()
    as_of = anchor.isoformat()
    cache_path = str(getattr(config, "breadth_cache_path", DEFAULT_CACHE_PATH) or DEFAULT_CACHE_PATH)
    conn = _cache_connect(cache_path)
    warnings: list[str] = []

    wanted = _business_days(anchor, max(lookback, 5))
    start_iso, end_iso = wanted[0].isoformat(), wanted[-1].isoformat()

    views: list[MarketBreadthView] = []
    try:
        # KRX 인증 세션으로 직접 POST (krx_client 가 로그인·세션 관리, 요청은 to_thread).
        for market in ("KOSPI", "KOSDAQ"):
            cached = _cache_load(conn, market, start_iso, end_iso) if conn else []
            have = {d.date for d in cached}
            missing = [d for d in wanted if d.isoformat() not in have]
            # 최신일 우선 + bounded — 오늘은 항상 포함.
            missing = sorted(missing, reverse=True)[:max_fetch]
            fetched: list[DailyBreadth] = []
            for d in sorted(missing):
                db = await _fetch_day(config, market, d)
                if db is not None:
                    fetched.append(db)
                    if conn:
                        _cache_upsert(conn, db)
                await asyncio.sleep(0.2)
            if conn and fetched:
                conn.commit()
            series = cached + fetched
            if not series:
                warnings.append(f"{market}: breadth 데이터 없음")
                continue
            view = summarize_market(
                series, (index_closes or {}).get(market),
            )
            if view:
                views.append(view)
    except Exception as e:  # pragma: no cover
        logger.warning("[breadth] fetch 실패 (graceful skip): %s", e)
        warnings.append(f"fetch 예외: {e}")
    finally:
        if conn:
            conn.close()

    snap = BreadthSnapshot(as_of=as_of, views=views, warnings=warnings)
    snap.key_figures = build_key_figures(views, as_of)
    snap.charts = build_charts(views)
    logger.info(
        "[breadth] %s — markets=%d kf=%d charts=%d warn=%d",
        as_of, len(views), len(snap.key_figures), len(snap.charts), len(snap.warnings),
    )
    return snap


# ──────────────────────────────────────────────────────────────────────────
# CLI — python -m src.tools.breadth_fetcher [YYYYMMDD] | backfill --days N
# ──────────────────────────────────────────────────────────────────────────
def _load_config():  # pragma: no cover
    """CLI 용 — .env 의 KRX_ID/KRX_PW 를 읽기 위해 Config 구성(실패 시 None)."""
    try:
        from src.config import Config
        return Config()
    except Exception as e:
        print(f"[warn] Config 로드 실패({e}) — KRX 로그인 없이 진행(데이터 안 나올 수 있음)")
        return None


def _main() -> None:  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO)
    cfg = _load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        days = 120
        if "--days" in sys.argv:
            try:
                days = int(sys.argv[sys.argv.index("--days") + 1])
            except (ValueError, IndexError):
                pass
        snap = asyncio.run(fetch_market_breadth_snapshot(config=cfg, lookback=days, max_fetch=days))
        print(f"backfill done — markets={len(snap.views)} warnings={snap.warnings}")
        for v in snap.views:
            print(f"  {v.market}: {len(v.series)}일 적재, 최신 {v.last.date} "
                  f"하락비율 {v.dr_last:.1f}%")
        return
    anchor = date.today()
    if len(sys.argv) > 1:
        try:
            anchor = datetime.strptime(sys.argv[1], "%Y%m%d").date()
        except ValueError:
            print("usage: python -m src.tools.breadth_fetcher [YYYYMMDD] | backfill --days N")
            return
    snap = asyncio.run(fetch_market_breadth_snapshot(anchor_date=anchor, config=cfg))
    print(f"\n=== 시장 등락 종목 수 ({snap.as_of}) ===  warnings={snap.warnings}")
    for v in snap.views:
        print(f"\n[{v.market}] 기준 {v.last.date}")
        print(f"  상승 {v.last.up} / 하락 {v.last.down} / 보합 {v.last.flat} (총 {v.last.total})")
        print(f"  하락비율 당일 {v.dr_last:.1f}% · 5일 {v.dr_avg5:.1f}% · 20일 {v.dr_avg20:.1f}% → {v.trend}")
        print(f"  상관 {v.corr}")
    print(f"\n--- key_figures ({len(snap.key_figures)}) ---")
    for kf in snap.key_figures:
        print(f"• {kf['label']}: {kf['value']}\n    {kf['context']}")


if __name__ == "__main__":  # pragma: no cover
    _main()
