"""IV 스큐 일별 캐시(skew_cache SQLite) → 타임라인 웹페이지용 JS 데이터 export.

`samples/iv_skew_timeline.html` 이 `window.SKEW_DATA` 를 읽어 날짜 슬라이더로
스큐 곡선이 어떻게 변해 왔는지 애니메이션한다. 이 스크립트는 VM(봇 가동기)의
실데이터 캐시(`data/iv_skew.sqlite`, store_skew 가 매 장마감 브리핑마다 적재)를
그 페이지가 읽을 수 있는 `samples/iv_skew_data.js` 로 결정적으로 변환한다.

LLM 0, 네트워크 0 — 순수 SQLite 읽기. 캐시가 비어 있으면 먼저 backfill:

    cd ~/agents_reviewer && source venv/bin/activate
    python -m src.tools.derivatives_fetcher skew-backfill --days 30
    python scripts/export_skew_timeline.py

ATM IV 는 캐시에 현물가가 없으므로 스큐 바닥(풋·콜 IV 가 가장 가까운 행사가)에서
근사한다 — drawIvSkew 의 ATM 기준선과 같은 직관(등가격 변동성 수평선).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _fmt_expiry(yyyymm: str) -> str:
    """'202607' → '2026년 7월물'. 못 알아보면 원문."""
    if len(yyyymm) >= 6 and yyyymm[:6].isdigit():
        return f"{yyyymm[:4]}년 {int(yyyymm[4:6])}월물"
    return yyyymm


def _atm_iv(points: list[dict]) -> float | None:
    """스큐 점들에서 등가격(ATM) IV 근사.

    풋·콜 IV 가 가장 가까운 행사가(스마일 바닥)의 두 IV 평균. 한쪽만 있으면
    중앙 행사가의 IV. drawIvSkew 가 payload.atm_iv 로 받는 값과 같은 역할.
    """
    puts = {p["strike"]: p["iv"] for p in points if p["type"] == "put"}
    calls = {p["strike"]: p["iv"] for p in points if p["type"] == "call"}
    both = sorted(set(puts) & set(calls))
    if both:
        k = min(both, key=lambda s: abs(puts[s] - calls[s]))
        return round((puts[k] + calls[k]) / 2.0, 1)
    strikes = sorted({p["strike"] for p in points})
    if not strikes:
        return None
    mid = strikes[len(strikes) // 2]
    ivs = [p["iv"] for p in points if p["strike"] == mid]
    return round(sum(ivs) / len(ivs), 1) if ivs else None


def build_payload(db_path: str) -> dict:
    """skew SQLite → window.SKEW_DATA 페이로드(만기별·일자별 스큐 점 + ATM)."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT date, expiry, opt_type, strike, iv FROM skew "
            "ORDER BY expiry ASC, date ASC, strike ASC"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    # expiry → date → [points]
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for date, expiry, opt_type, strike, iv in rows:
        grouped[expiry][date].append(
            {"strike": float(strike), "iv": round(float(iv), 1), "type": str(opt_type)}
        )

    expiries: dict[str, dict] = {}
    for expiry, by_date in grouped.items():
        dates = sorted(by_date)
        expiries[expiry] = {
            "label": _fmt_expiry(expiry),
            "dates": dates,
            "byDate": {
                d: {"points": by_date[d], "atm": _atm_iv(by_date[d])} for d in dates
            },
        }

    # 기본 만기 = 일자 수가 가장 많은(가장 활발히 적재된) 만기.
    default_expiry = (
        max(expiries, key=lambda e: len(expiries[e]["dates"])) if expiries else None
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "KRX 종가에서 산출 (skew_cache)",
        "expiries": expiries,
        "default_expiry": default_expiry,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="IV 스큐 타임라인 데이터 export")
    ap.add_argument(
        "--db", default="data/iv_skew.sqlite", help="skew_cache SQLite 경로"
    )
    ap.add_argument(
        "--out", default="samples/iv_skew_data.js", help="출력 JS 파일 경로"
    )
    args = ap.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(
            f"[error] 캐시 없음: {args.db}\n"
            "  먼저 backfill: python -m src.tools.derivatives_fetcher skew-backfill --days 30"
        )

    payload = build_payload(args.db)
    n_exp = len(payload["expiries"])
    n_dates = sum(len(e["dates"]) for e in payload["expiries"].values())
    if not n_exp:
        raise SystemExit(f"[error] 캐시가 비어 있음: {args.db} (backfill 필요)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "// 자동 생성 — scripts/export_skew_timeline.py (직접 편집 금지)\n"
        "window.SKEW_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(
        f"[ok] {args.out} 작성 — 만기 {n_exp}종 / 총 {n_dates}일자 "
        f"(기본 만기 {payload['default_expiry']})"
    )
    print("  → samples/iv_skew_timeline.html 을 브라우저로 열면 실데이터로 표시됩니다.")


if __name__ == "__main__":
    main()
