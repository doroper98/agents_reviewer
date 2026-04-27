"""WatchlistRegistry — SQLite CRUD for WatchSignal persistence.

V3 Step 5-B (v2.9.5). Standard library only (sqlite3) — 의존성 추가 0.

Sync API on top of sqlite3 — sqlite3 자체가 fast (≤ ms 수준) 라 asyncio event loop 차단 영향
무시 가능. 동기 함수를 그대로 async 컨텍스트에서 호출.

Anti-pattern #11 회피: 본 registry 가 SSOT. ``ScenarioAnalysis.watch_signals`` (dict 배열) 은
``orchestrator`` 단계에서 ``convert_watch_signals()`` 로 변환되어 ``register()`` 됨.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from src.models import WatchSignal

logger = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "db_schema.sql")


class WatchlistRegistry:
    """SQLite-backed Watchlist registry.

    Schema is in ``db_schema.sql``. The registry is process-shared via the bot main loop
    (one instance per bot process). Concurrent writes from the asyncio monitor task
    are protected by sqlite3 internal locking + WAL mode.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self._initialize()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        logger.info("[watchlist] Registry initialized at %s", self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API — CRUD
    # ------------------------------------------------------------------

    def register(self, signal: WatchSignal) -> bool:
        """Insert (or no-op on duplicate signal_id). Returns True if newly inserted."""
        created_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO watchsignals
                (signal_id, description, measurement, direction, deadline,
                 follow_up_action, parent_report_url, parent_report_id,
                 parent_chat_id, fired, fired_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id, signal.description, signal.measurement,
                    signal.direction, signal.deadline, signal.follow_up_action,
                    signal.parent_report_url, signal.parent_report_id,
                    signal.parent_chat_id,
                    int(signal.fired), signal.fired_at, created_at,
                ),
            )
            return cur.rowcount > 0

    def get(self, signal_id: str) -> WatchSignal | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM watchsignals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
        return _row_to_signal(row) if row else None

    def list_active(self) -> list[WatchSignal]:
        """모든 채팅 통틀어 미발화(active) 신호 — monitor task 가 호출."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchsignals WHERE fired = 0 ORDER BY deadline ASC"
            ).fetchall()
        return [_row_to_signal(r) for r in rows]

    def list_active_for_chat(self, chat_id: int) -> list[WatchSignal]:
        """특정 채팅의 미발화 신호 — ``/watchlist`` 명령 응답에 사용."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchsignals "
                "WHERE fired = 0 AND parent_chat_id = ? "
                "ORDER BY deadline ASC",
                (chat_id,),
            ).fetchall()
        return [_row_to_signal(r) for r in rows]

    def list_fired(self, limit: int = 50) -> list[WatchSignal]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchsignals WHERE fired = 1 "
                "ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_signal(r) for r in rows]

    def mark_fired(
        self, signal_id: str, fired_at: str | None = None,
        new_direction: str | None = None,
    ) -> WatchSignal | None:
        """Mark a signal fired. ``new_direction`` 가 주어지면 동시 갱신 (수동 fire 시).

        Returns the updated WatchSignal, or None if signal_id not found.
        """
        if fired_at is None:
            fired_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            if new_direction is not None:
                conn.execute(
                    "UPDATE watchsignals SET fired = 1, fired_at = ?, direction = ? "
                    "WHERE signal_id = ? AND fired = 0",
                    (fired_at, new_direction, signal_id),
                )
            else:
                conn.execute(
                    "UPDATE watchsignals SET fired = 1, fired_at = ? "
                    "WHERE signal_id = ? AND fired = 0",
                    (fired_at, signal_id),
                )
            row = conn.execute(
                "SELECT * FROM watchsignals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
        return _row_to_signal(row) if row else None

    def count_active(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM watchsignals WHERE fired = 0"
            ).fetchone()
        return int(n)

    def count_total(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM watchsignals").fetchone()
        return int(n)


def _row_to_signal(row: sqlite3.Row) -> WatchSignal:
    return WatchSignal(
        signal_id=row["signal_id"],
        description=row["description"],
        measurement=row["measurement"] or "",
        direction=row["direction"],
        deadline=row["deadline"],
        follow_up_action=row["follow_up_action"] or "",
        parent_report_url=row["parent_report_url"] or "",
        parent_report_id=row["parent_report_id"] or "",
        parent_chat_id=int(row["parent_chat_id"] or 0),
        fired=bool(row["fired"]),
        fired_at=row["fired_at"],
    )
