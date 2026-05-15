#!/usr/bin/env python3
"""verify_market_fetcher — VM 에서 market_fetcher.py 가 실데이터를 fetch 하는지
독립 검증. .env 의 FRED_API_KEY / ECOS_API_KEY 를 읽어 6 종목 fetch 후 결과 출력.

사용:
    cd ~/agents_reviewer
    source venv/bin/activate
    python scripts/verify_market_fetcher.py

성공 시 6 종목 모두 ✅ 표시. 실패한 종목은 ❌ + 사유 (key 누락 / HTTP error /
빈 응답 등). 봇 재시작 *전* 키가 정상 작동하는지 확인하는 용도.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_config
from src.tools.market_fetcher import fetch_many


INSTRUMENTS = [
    "코스피",        # KRX (무인증)
    "삼성전자",      # KRX (무인증)
    "달러인덱스",    # FRED
    "미국채 1Y",     # FRED
    "WTI",          # FRED
    "국고 10년",     # ECOS
]


async def main() -> int:
    config = get_config()

    print("=" * 70)
    print(" Market Fetcher 검증 — 1M 기간 fetch")
    print("=" * 70)
    print(f" FRED_API_KEY : {'설정됨' if config.fred_api_key else '⚠️ 비어있음'}")
    print(f" ECOS_API_KEY : {'설정됨' if config.ecos_api_key else '⚠️ 비어있음'}")
    print(f" KRX_API_KEY  : {'설정됨' if config.krx_api_key else '(무인증 — 정상)'}")
    print("=" * 70)

    series_list = await fetch_many(INSTRUMENTS, period="1M", config=config)

    ok = 0
    fail = 0
    for inst, s in zip(INSTRUMENTS, series_list):
        if s.data:
            first = s.data[0]
            last = s.data[-1]
            print(
                f" ✅ {inst:12s} [{s.source:4s}] {len(s.data):3d} bars  "
                f"{first.date} ({first.close:>12,.2f}) → {last.date} ({last.close:>12,.2f})"
            )
            ok += 1
        else:
            print(
                f" ❌ {inst:12s} [{s.source or '???':4s}] 빈 응답 "
                f"— code={s.code or '?'} period={s.start_date}~{s.end_date}"
            )
            fail += 1

    print("=" * 70)
    print(f" 결과: {ok}/{len(INSTRUMENTS)} 성공, {fail} 실패")
    print("=" * 70)
    if fail:
        print(
            "\n실패한 종목이 있으면:\n"
            " - ❌ FRED 종목: .env 의 FRED_API_KEY 확인 (https://fred.stlouisfed.org/docs/api/api_key.html)\n"
            " - ❌ ECOS 종목: .env 의 ECOS_API_KEY 확인 (https://ecos.bok.or.kr/api/)\n"
            " - ❌ KRX 종목: 네트워크 (data.krx.co.kr) 접근 확인 — 방화벽/프록시\n"
            " - bot.log 에서 [market_fetcher] warning 라인 검색"
        )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
