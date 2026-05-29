"""Daily Briefing Scheduler — v5.1.0.

봇 프로세스 안에서 도는 asyncio task. 매일 지정 시각 (기본 06:00 KST) 에 깨어나
구독한 텔레그램 채팅에 "간밤 산업·지정학·정치·전쟁 이슈" 심층 보고서를 자동 송신.

Public API:
- ``BriefingSubscriberRegistry`` — SQLite-backed 구독 저장소 (``/briefing_on`` 명령으로 등록).
- ``run_daily_briefing_loop()`` — 봇 시작 시 ``asyncio.create_task(...)`` 로 띄우는 background loop.
"""

from src.scheduler.daily_briefing import run_daily_briefing_loop
from src.scheduler.market_briefing import run_market_briefing_loop
from src.scheduler.subscriptions import (
    BriefingSubscriberRegistry,
    MarketBriefSubscriberRegistry,
)

__all__ = [
    "BriefingSubscriberRegistry",
    "MarketBriefSubscriberRegistry",
    "run_daily_briefing_loop",
    "run_market_briefing_loop",
]
