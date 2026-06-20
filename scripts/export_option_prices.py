"""과거 옵션 *실제 종가(프리미엄=가격)* 를 KRX 에서 재수집 → 타임라인 페이지용 JS.

IV 스큐 캐시(iv_skew.sqlite)에는 IV 만 있고 옵션 종가는 안 들어있다. 이 스크립트는
캐시에 들어있는 *날짜들* 에 대해 KRX 옵션 체인을 그 날짜로 다시 조회해, 행사가·타입별
**실제 종가(TDD_CLSPRC = 프리미엄 = 가격)** 를 받아 `samples/iv_skew_prices.js`
(`window.OPTION_PRICES`) 로 내보낸다. 페이지의 세로축 '프리미엄(가격)' 토글이 이 실측을
우선 쓰고, 없는 점만 BS 이론가로 폴백한다.

derivatives_fetcher 의 검증된 엔드포인트/파서를 그대로 재사용한다 (봇 본체 무변경).
KRX 인증·네트워크가 정상일 때 VM 에서 1회 실행:

    cd ~/agents_reviewer && source venv/bin/activate
    python scripts/export_option_prices.py

KRX 타임아웃 등으로 일부 날짜가 실패하면 그 날짜만 건너뛰고(페이지는 그 점만 이론가
폴백) 나머지는 정상 기록한다 (graceful).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.tools.derivatives_fetcher import (
    BLD_DERIV_PRICES,
    PROD_KOSPI200_OPT,
    parse_option_rows,
)
from src.tools.krx_client import post_json_rows


def _cache_dates(db_path: str) -> list[str]:
    """스큐 캐시에 들어있는 distinct 날짜(ISO) — 페이지가 그리는 날짜와 동일."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT DISTINCT date FROM skew ORDER BY date").fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


async def _fetch_day(config, iso_date: str) -> list[dict]:
    """해당 날짜 KOSPI200 옵션 체인 전종목 → parse_option_rows 결과(프리미엄 포함)."""
    trd_dd = iso_date.replace("-", "")
    rows = await post_json_rows(
        config,
        BLD_DERIV_PRICES,
        {
            "locale": "ko_KR", "prodId": PROD_KOSPI200_OPT,
            "trdDd": trd_dd, "mktTpCd": "T", "rghtTpCd": "T",
            "share": "1", "money": "1",
        },
    )
    return parse_option_rows(rows)


async def build(db_path: str) -> dict:
    """캐시 날짜별로 KRX 재조회 → {expiry: {date: {'type|strike': premium}}}."""
    try:
        from src.config import Config
        config = Config()
    except Exception as e:  # pragma: no cover
        print(f"[warn] Config 로드 실패({e}) — KRX 로그인 없이 진행(대개 실패)")
        config = None

    dates = _cache_dates(db_path)
    print(f"대상 {len(dates)}일자: {dates[0]} ~ {dates[-1]}")

    prices: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    ok = 0
    for d in dates:
        try:
            parsed = await _fetch_day(config, d)
        except Exception as e:
            print(f"  {d} — 실패(건너뜀): {e}")
            continue
        n = 0
        for o in parsed:
            prem, strike, exp, otype = o["premium"], o["strike"], o["expiry"], o["option_type"]
            if prem is None or prem <= 0 or strike is None:
                continue
            prices[exp][d][f"{otype}|{strike:g}"] = round(float(prem), 2)
            n += 1
        if n:
            ok += 1
        print(f"  {d} — 옵션 {n}건 종가 수집")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "KRX 정보데이터시스템 옵션 종가(TDD_CLSPRC)",
        "ok_days": ok, "total_days": len(dates),
        "byExpiry": {e: dict(v) for e, v in prices.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="과거 옵션 실제 종가 → 타임라인 페이지 JS")
    ap.add_argument("--db", default="data/iv_skew.sqlite", help="skew_cache SQLite 경로")
    ap.add_argument("--out", default="samples/iv_skew_prices.js", help="출력 JS 경로")
    args = ap.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"[error] 캐시 없음: {args.db}")

    payload = asyncio.run(build(args.db))
    if not payload["ok_days"]:
        raise SystemExit(
            "[error] 종가를 한 건도 못 받았습니다 — KRX 로그인/네트워크 확인 후 재시도.\n"
            "  (페이지는 그동안 BS 이론가로 계속 동작합니다.)"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "// 자동 생성 — scripts/export_option_prices.py (직접 편집 금지)\n"
        "window.OPTION_PRICES = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(
        f"[ok] {args.out} — {payload['ok_days']}/{payload['total_days']}일자 실제 종가 기록.\n"
        "  페이지 세로축 '프리미엄(가격)'이 이론가 대신 실제 종가로 표시됩니다."
    )


if __name__ == "__main__":
    main()
