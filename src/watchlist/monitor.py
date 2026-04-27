"""Watchlist monitor — asyncio background task in the bot process.

V3 Step 5-B (v2.9.5).

본 task 는 1시간(기본) 주기로 등록된 active signal 들을 순회하며 ``deadline`` 이 도래한 항목을
``ambiguous`` 방향으로 자동 발화 (auto-fire) + 텔레그램 알림 콜백 호출.

외부 시장 데이터 폴링은 본 step 밖 — 발화 트리거는 deadline 자동 + 사용자 ``/fire`` 수동 둘만.

봇 재시작 시 ``WatchlistRegistry.list_active()`` 로 DB → 메모리 task 재구성하는 패턴 (B 보강).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Awaitable, Callable

from src.models import WatchSignal
from src.watchlist.registry import WatchlistRegistry

logger = logging.getLogger(__name__)


# 알림 콜백 타입: WatchSignal 을 받아 텔레그램으로 전송하는 비동기 함수.
NotifyFn = Callable[[WatchSignal], Awaitable[None]]


async def run_monitor_loop(
    registry: WatchlistRegistry,
    notify_fn: NotifyFn,
    interval_seconds: int = 3600,
    today_provider: Callable[[], date] | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> None:
    """Background loop. 봇 시작 시 ``asyncio.create_task(run_monitor_loop(...))`` 로 띄움.

    Args:
        registry: 공유 WatchlistRegistry 인스턴스.
        notify_fn: 발화된 signal 을 텔레그램으로 전송하는 비동기 콜백.
        interval_seconds: 폴링 주기. 기본 1시간.
        today_provider / now_provider: 테스트용 시간 mock. 기본은 시스템 시간.
    """
    today_fn = today_provider or date.today
    now_fn = now_provider or datetime.utcnow
    logger.info(
        "[watchlist] Monitor loop starting (interval=%ds, active=%d)",
        interval_seconds, registry.count_active(),
    )
    while True:
        try:
            fired_count = await tick_once(registry, notify_fn, today_fn, now_fn)
            if fired_count:
                logger.info(
                    "[watchlist] tick: %d signal(s) auto-fired this cycle", fired_count
                )
        except asyncio.CancelledError:
            logger.info("[watchlist] Monitor loop cancelled — shutting down")
            raise
        except Exception as e:
            logger.warning("[watchlist] tick error: %s", e)
        await asyncio.sleep(interval_seconds)


async def tick_once(
    registry: WatchlistRegistry,
    notify_fn: NotifyFn,
    today_fn: Callable[[], date],
    now_fn: Callable[[], datetime],
) -> int:
    """Single iteration — 본 step 의 자동 발화 핵심 로직. 테스트에서 직접 호출 가능.

    Returns: 본 cycle 에서 자동 발화된 신호 수.
    """
    today = today_fn()
    now_iso = now_fn().isoformat()
    active = registry.list_active()
    fired = 0
    for sig in active:
        try:
            sig_deadline = date.fromisoformat(sig.deadline)
        except ValueError:
            logger.warning(
                "[watchlist] signal %s has invalid deadline %r; skipping",
                sig.signal_id, sig.deadline,
            )
            continue
        if sig_deadline > today:
            continue
        # Deadline reached — auto-fire as ambiguous (unless already a directional signal).
        new_direction = sig.direction if sig.direction != "ambiguous" else "ambiguous"
        updated = registry.mark_fired(sig.signal_id, fired_at=now_iso, new_direction=new_direction)
        if updated is None:
            continue
        try:
            await notify_fn(updated)
            fired += 1
            logger.info(
                "[watchlist] auto-fired %s (deadline=%s, direction=%s)",
                updated.signal_id, updated.deadline, updated.direction,
            )
        except Exception as e:
            logger.warning(
                "[watchlist] notify failed for %s: %s (DB 등록은 유지, 알림만 실패)",
                updated.signal_id, e,
            )
    return fired


def format_telegram_alert(signal: WatchSignal, parent_title: str = "") -> str:
    """Standard telegram alert text per spec template."""
    return (
        "🔔 감시 신호 발생\n"
        f"사건: {parent_title or signal.parent_report_id or '(unknown)'}\n"
        f"신호: {signal.description} → {signal.direction}\n"
        f"원 보고서: {signal.parent_report_url or '(없음)'}\n"
        f"권장 후속: {signal.follow_up_action or '(미지정)'}"
    )
