"""Unit tests for V3 Step 5-B — Watchlist Registry + monitor + converter.

Run:
    python -m pytest src/tests/test_watchlist.py -v
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import date, datetime, timedelta

import pytest

from src.models import WatchSignal
from src.watchlist.converter import convert_watch_signals
from src.watchlist.monitor import format_telegram_alert, tick_once
from src.watchlist.registry import WatchlistRegistry


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def tmp_db():
    """Per-test sqlite DB. Use file-based (not :memory:) to test schema script."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture
def registry(tmp_db) -> WatchlistRegistry:
    return WatchlistRegistry(tmp_db)


def _make_signal(
    signal_id: str = "WS-T-001",
    deadline_days_offset: int = 30,
    chat_id: int = 123,
    direction: str = "ambiguous",
) -> WatchSignal:
    deadline = (date.today() + timedelta(days=deadline_days_offset)).isoformat()
    return WatchSignal(
        signal_id=signal_id,
        description="DXY > 95",
        measurement="DXY 일봉 종가",
        direction=direction,  # type: ignore[arg-type]
        deadline=deadline,
        follow_up_action="후속 분석",
        parent_report_url="https://x.dev/r1",
        parent_report_id="r1",
        parent_chat_id=chat_id,
    )


# ----------------------------------------------------------------------
# WatchSignal model
# ----------------------------------------------------------------------


class TestWatchSignalModel:
    def test_minimal_construction(self):
        ws = _make_signal()
        assert ws.fired is False
        assert ws.fired_at is None

    def test_invalid_direction_rejected(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            WatchSignal(
                signal_id="X", description="d",
                direction="not_a_direction",  # type: ignore[arg-type]
                deadline="2026-12-31",
            )


# ----------------------------------------------------------------------
# Registry CRUD
# ----------------------------------------------------------------------


class TestWatchlistRegistry:
    def test_register_then_get(self, registry):
        ws = _make_signal()
        assert registry.register(ws) is True
        got = registry.get("WS-T-001")
        assert got is not None
        assert got.description == ws.description
        assert got.fired is False

    def test_register_idempotent(self, registry):
        ws = _make_signal()
        assert registry.register(ws) is True
        assert registry.register(ws) is False  # duplicate signal_id → no-op
        assert registry.count_total() == 1

    def test_list_active_excludes_fired(self, registry):
        ws1 = _make_signal("WS-T-001")
        ws2 = _make_signal("WS-T-002")
        registry.register(ws1)
        registry.register(ws2)
        registry.mark_fired("WS-T-001")
        active = registry.list_active()
        assert len(active) == 1
        assert active[0].signal_id == "WS-T-002"

    def test_list_active_for_chat_filters(self, registry):
        a = _make_signal("WS-A", chat_id=1)
        b = _make_signal("WS-B", chat_id=2)
        c = _make_signal("WS-C", chat_id=2)
        for s in (a, b, c):
            registry.register(s)
        chat2 = registry.list_active_for_chat(2)
        ids = sorted(s.signal_id for s in chat2)
        assert ids == ["WS-B", "WS-C"]

    def test_mark_fired_sets_timestamp_and_optional_direction(self, registry):
        registry.register(_make_signal("WS-1", direction="ambiguous"))
        updated = registry.mark_fired("WS-1", new_direction="rejects_base")
        assert updated is not None
        assert updated.fired is True
        assert updated.fired_at  # set
        assert updated.direction == "rejects_base"

    def test_count_active_after_mixed(self, registry):
        registry.register(_make_signal("WS-1"))
        registry.register(_make_signal("WS-2"))
        registry.register(_make_signal("WS-3"))
        registry.mark_fired("WS-2")
        assert registry.count_active() == 2
        assert registry.count_total() == 3

    def test_get_unknown_returns_none(self, registry):
        assert registry.get("does-not-exist") is None


# ----------------------------------------------------------------------
# Converter — ScenarioAnalysis.watch_signals (dict[]) → list[WatchSignal]
# ----------------------------------------------------------------------


class TestConverter:
    def test_typical_dict_list(self):
        sigs = [
            {"signal": "DXY 105 돌파", "description": "DXY 종가",
             "indicates": "달러 강세 위험"},
            {"signal": "한미 금리차 좁힘", "description": "<100bps",
             "indicates": "안정 지속"},
        ]
        out = convert_watch_signals(sigs, parent_report_id="r1", parent_chat_id=42)
        assert len(out) == 2
        assert all(w.parent_chat_id == 42 for w in out)
        assert all(w.parent_report_id == "r1" for w in out)
        # direction inference
        directions = {w.description: w.direction for w in out}
        assert directions["DXY 105 돌파"] == "rejects_base"  # "위험" 어휘
        assert directions["한미 금리차 좁힘"] == "confirms_base"  # "지속" 어휘

    def test_empty_input(self):
        assert convert_watch_signals([]) == []

    def test_skip_missing_signal_field(self):
        sigs = [
            {"signal": "ok"},
            {"description": "no signal"},  # 'signal' 필드 없음
            {"signal": ""},                 # 빈 문자열
        ]
        out = convert_watch_signals(sigs, parent_report_id="r")
        assert len(out) == 1
        assert out[0].description == "ok"

    def test_default_deadline_30_days(self):
        sigs = [{"signal": "test"}]
        out = convert_watch_signals(sigs, parent_report_id="r")
        deadline_dt = date.fromisoformat(out[0].deadline)
        delta = (deadline_dt - date.today()).days
        assert 29 <= delta <= 31  # default 30 ± 일자 경계

    def test_idempotent_signal_ids(self):
        """같은 보고서 + 같은 signal 텍스트 → 같은 signal_id (deterministic hash)."""
        sigs = [{"signal": "DXY 105"}]
        out1 = convert_watch_signals(sigs, parent_report_id="r1")
        out2 = convert_watch_signals(sigs, parent_report_id="r1")
        assert out1[0].signal_id == out2[0].signal_id


# ----------------------------------------------------------------------
# Monitor — auto-fire on deadline, with mocked clock
# ----------------------------------------------------------------------


class TestMonitor:
    def test_auto_fire_on_deadline(self, registry):
        # Register one expired + one future signal.
        expired = _make_signal("WS-EXPIRED", deadline_days_offset=-1)
        future = _make_signal("WS-FUTURE", deadline_days_offset=10)
        registry.register(expired)
        registry.register(future)

        captured: list[WatchSignal] = []

        async def _notify(sig: WatchSignal) -> None:
            captured.append(sig)

        # Fixed clock at today.
        today = date.today()
        now = datetime.utcnow()
        fired = asyncio.run(tick_once(
            registry, _notify, lambda: today, lambda: now,
        ))
        assert fired == 1
        assert len(captured) == 1
        assert captured[0].signal_id == "WS-EXPIRED"
        assert captured[0].fired is True
        # Future signal still active.
        assert registry.get("WS-FUTURE").fired is False

    def test_notify_failure_does_not_unfire(self, registry):
        """Telegram 송신 실패해도 DB 의 fired 상태는 유지 (recovery 용)."""
        registry.register(_make_signal("WS-X", deadline_days_offset=-5))

        async def _notify(sig: WatchSignal) -> None:
            raise RuntimeError("telegram down")

        today = date.today()
        now = datetime.utcnow()
        # tick_once should not raise even though notify_fn raises.
        fired = asyncio.run(tick_once(
            registry, _notify, lambda: today, lambda: now,
        ))
        # fired 카운트는 알림 성공한 것만 — 0 (알림 실패).
        assert fired == 0
        # 그러나 DB 는 이미 fired 처리됨 (재진입 시 또 fire 시도하지 않게).
        sig = registry.get("WS-X")
        assert sig.fired is True

    def test_no_op_when_no_active(self, registry):
        async def _notify(_): pass
        today = date.today()
        now = datetime.utcnow()
        fired = asyncio.run(tick_once(
            registry, _notify, lambda: today, lambda: now,
        ))
        assert fired == 0


# ----------------------------------------------------------------------
# Bot restart simulation — DB persistence + load_active_signals 패턴
# ----------------------------------------------------------------------


class TestBotRestartPersistence:
    def test_active_signals_survive_registry_reopen(self, tmp_db):
        """봇 재시작 = registry 재초기화. 이전 active 신호가 그대로 보여야 함."""
        # First "boot": register two signals, fire one.
        reg1 = WatchlistRegistry(tmp_db)
        reg1.register(_make_signal("WS-ALIVE"))
        reg1.register(_make_signal("WS-DEAD"))
        reg1.mark_fired("WS-DEAD")
        assert reg1.count_active() == 1

        # Second "boot": new instance pointing at same DB.
        reg2 = WatchlistRegistry(tmp_db)
        active = reg2.list_active()
        assert len(active) == 1
        assert active[0].signal_id == "WS-ALIVE"
        # Total count includes fired one.
        assert reg2.count_total() == 2


# ----------------------------------------------------------------------
# Telegram alert formatting (spec template exact match)
# ----------------------------------------------------------------------


class TestAlertFormat:
    def test_alert_text_matches_spec(self):
        sig = _make_signal("WS-FMT", direction="rejects_base")
        text = format_telegram_alert(sig, parent_title="환율 분석")
        # Spec template:
        #   🔔 감시 신호 발생
        #   사건: {parent_report_title}
        #   신호: {description} → {direction}
        #   원 보고서: {parent_report_url}
        #   권장 후속: {follow_up_action}
        assert text.startswith("🔔 감시 신호 발생")
        assert "사건: 환율 분석" in text
        assert "신호: DXY > 95 → rejects_base" in text
        assert "원 보고서: https://x.dev/r1" in text
        assert "권장 후속: 후속 분석" in text
