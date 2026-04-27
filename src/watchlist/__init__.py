"""Watchlist Registry — V3 Step 5-B (v2.9.5).

ScenarioArchitect 가 산출한 감시 신호를 보고서 텍스트로만 남기지 않고 (Anti-pattern #11)
SQLite DB 에 등록하고, 봇 프로세스 안의 asyncio task 가 deadline 도래 시 자동 발화한다.
사용자가 ``/fire <signal_id>`` 로 수동 발화하는 경로도 존재.

본 step 은 외부 시장 데이터 자동 폴링은 *하지 않음* — deadline + 수동 발화 두 트리거만.
시장 데이터 폴링은 v3.1+ FUT 트랙.

Public API:
- ``WatchlistRegistry`` — SQLite CRUD
- ``convert_watch_signals()`` — ScenarioAnalysis.watch_signals (dict) → WatchSignal
- ``run_monitor_loop()`` — 봇 프로세스 안에서 도는 background task
"""

from src.watchlist.converter import convert_watch_signals
from src.watchlist.monitor import run_monitor_loop
from src.watchlist.registry import WatchlistRegistry

__all__ = ["WatchlistRegistry", "convert_watch_signals", "run_monitor_loop"]
