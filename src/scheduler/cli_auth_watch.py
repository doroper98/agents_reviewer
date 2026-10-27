"""Claude CLI 인증 사전 점검 — 브리핑 N분 전에 로그인 만료를 먼저 알린다 (v8.7.1).

봇 프로세스 안에서 도는 asyncio task (daily_briefing / market_briefing 과 같은 패턴).
켜진 브리핑마다 ``브리핑 시각 - CLI_AUTH_WATCH_LEAD_MIN`` 에 깨어나
``claude -p ping`` 을 돌린다. 인증이 만료됐으면 브리핑 구독자에게 복구 명령을 보내
*브리핑이 실패하기 전에* 고칠 시간을 준다 (VM-AP-14 — 2026-09-27 부터 한 달간
브리핑 전면 실패를 아무도 모른 사고).

- 경고는 인증 만료일 때만 보낸다. 타임아웃·CLI 부재 같은 다른 실패는 로그만 남긴다
  (오경보로 경고가 무시되는 것을 막는다).
- 만료가 이어지면 점검 시각마다 다시 보낸다 — 고칠 때까지 조용해지지 않는 게 목적.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from src.scheduler.daily_briefing import _next_trigger
from src.tools.cli_auth import CLI_AUTH_FIX, CliAuthProbe, probe_cli_auth

logger = logging.getLogger(__name__)

SendTextFn = Callable[[int, str], Awaitable[None]]
RecipientsFn = Callable[[], list[int]]
ProbeFn = Callable[[], Awaitable[CliAuthProbe]]

# 브리핑 시각과 겹치면 점검이 브리핑과 경쟁한다. 너무 이르면 그사이 만료를 놓친다.
LEAD_MIN_FLOOR = 5
LEAD_MIN_CEIL = 720


class AuthCheckSlot(BaseModel):
    """점검 대상 브리핑 하나."""

    label: str          # 경고 문구에 쓰는 이름 (예: "일일 브리핑")
    briefing_time: str  # 'HH:MM' — 브리핑 시각
    tz_name: str


def check_time_before(time_str: str, lead_min: int) -> str:
    """'HH:MM' 에서 lead_min 분 앞선 'HH:MM' (자정 넘김 처리)."""
    h, m = (int(x) for x in time_str.split(":", 1))
    total = (h * 60 + m - lead_min) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def clamp_lead(lead_min: int) -> int:
    return max(LEAD_MIN_FLOOR, min(LEAD_MIN_CEIL, int(lead_min)))


def next_check(
    slots: list[AuthCheckSlot], lead_min: int, now: datetime | None = None,
) -> tuple[datetime, AuthCheckSlot]:
    """다음 점검 시각과 그 대상 브리핑. slots 는 비어 있으면 안 된다."""
    best: tuple[datetime, AuthCheckSlot] | None = None
    for slot in slots:
        when = _next_trigger(
            check_time_before(slot.briefing_time, lead_min), slot.tz_name, now=now,
        )
        if best is None or when < best[0]:
            best = (when, slot)
    assert best is not None
    return best


def expired_alert(slot: AuthCheckSlot) -> str:
    return (
        f"⚠️ Claude CLI 로그인이 만료됐습니다.\n"
        f"이대로면 {slot.briefing_time} {slot.label}이 실패합니다.\n\n"
        f"{CLI_AUTH_FIX}"
    )


async def run_cli_auth_check_once(
    *,
    slot: AuthCheckSlot,
    recipients_fn: RecipientsFn,
    send_text_fn: SendTextFn,
    probe_fn: ProbeFn = probe_cli_auth,
) -> CliAuthProbe:
    """점검 1회. 만료면 수신자 전원에게 경고. 결과를 돌려준다."""
    probe = await probe_fn()
    if probe.ok:
        logger.info("[cli_auth_watch] CLI auth OK (before %s %s)", slot.briefing_time, slot.label)
        return probe
    if not probe.auth_expired:
        logger.warning(
            "[cli_auth_watch] CLI probe failed (not auth, no alert): %s", probe.detail,
        )
        return probe

    chat_ids = sorted(set(recipients_fn()))
    logger.warning(
        "[cli_auth_watch] CLI auth EXPIRED — alerting %d chat(s) before %s %s: %s",
        len(chat_ids), slot.briefing_time, slot.label, probe.detail,
    )
    text = expired_alert(slot)
    for chat_id in chat_ids:
        try:
            await send_text_fn(chat_id, text)
        except Exception as e:
            logger.warning("[cli_auth_watch] alert send failed for chat=%d: %s", chat_id, e)
    return probe


async def run_cli_auth_watch_loop(
    *,
    slots: list[AuthCheckSlot],
    recipients_fn: RecipientsFn,
    send_text_fn: SendTextFn,
    lead_min: int = 60,
    probe_fn: ProbeFn = probe_cli_auth,
) -> None:
    """Background loop. 봇 시작 시 ``asyncio.create_task(...)`` 로 띄운다."""
    if not slots:
        logger.info("[cli_auth_watch] no enabled briefing — watch loop not started")
        return
    lead = clamp_lead(lead_min)
    logger.info(
        "[cli_auth_watch] loop starting (lead=%dmin, slots=%s)",
        lead, [f"{s.label}@{s.briefing_time} {s.tz_name}" for s in slots],
    )
    while True:
        try:
            when, slot = next_check(slots, lead)
            now = datetime.now(ZoneInfo(slot.tz_name))
            sleep_sec = max(1.0, (when - now).total_seconds())
            logger.info(
                "[cli_auth_watch] next check at %s (before %s) — sleeping %.0fs",
                when.isoformat(), slot.label, sleep_sec,
            )
            await asyncio.sleep(sleep_sec)
        except asyncio.CancelledError:
            logger.info("[cli_auth_watch] loop cancelled — shutting down")
            raise

        try:
            await run_cli_auth_check_once(
                slot=slot, recipients_fn=recipients_fn,
                send_text_fn=send_text_fn, probe_fn=probe_fn,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("[cli_auth_watch] check error: %s", e, exc_info=True)
        # 같은 분에 다시 깨어나지 않도록 1분 넘겨서 다음 점검을 계산한다.
        await asyncio.sleep(61)
