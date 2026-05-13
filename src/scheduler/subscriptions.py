"""BriefingSubscriberRegistry — SQLite CRUD for daily briefing subscribers.

v5.1.0. ``WatchlistRegistry`` 와 동일 패턴: 표준 라이브러리 ``sqlite3`` 만, WAL 모드,
sync 함수 (sqlite 자체가 ms 단위라 asyncio 차단 없음).

Subscription 등록은 사용자가 ``/briefing_on`` 명령으로 그 채팅의 chat_id 를 저장하는
모델. 봇 재시작 후에도 활성 구독은 자연 복구 (DB 영속성).

``mode`` 필드는 ``token_budget.AnalysisMode`` 와 매칭 — orchestrator 가 그대로
``run_analysis(mode=...)`` 에 전달. 디폴트 ``'deep'``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from src.token_budget import AnalysisMode

logger = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "db_schema.sql")


class BriefingSubscriberRegistry:
    """SQLite-backed daily briefing subscriber registry."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        logger.info("[scheduler] Subscription registry initialized at %s", self.db_path)

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
    # Subscription CRUD
    # ------------------------------------------------------------------

    def subscribe(self, chat_id: int, mode: AnalysisMode = "deep") -> bool:
        """Insert or replace subscription. Returns True if newly inserted."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT chat_id FROM briefing_subscribers WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE briefing_subscribers SET mode = ? WHERE chat_id = ?",
                    (mode, chat_id),
                )
                return False
            conn.execute(
                "INSERT INTO briefing_subscribers (chat_id, subscribed_at, mode) "
                "VALUES (?, ?, ?)",
                (chat_id, now, mode),
            )
            return True

    def unsubscribe(self, chat_id: int) -> bool:
        """Remove subscription. Returns True if a row was removed."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM briefing_subscribers WHERE chat_id = ?", (chat_id,),
            )
            return cur.rowcount > 0

    def is_subscribed(self, chat_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM briefing_subscribers WHERE chat_id = ?", (chat_id,),
            ).fetchone()
        return row is not None

    def get_mode(self, chat_id: int) -> AnalysisMode | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mode FROM briefing_subscribers WHERE chat_id = ?", (chat_id,),
            ).fetchone()
        return row["mode"] if row else None

    def list_all(self) -> list[tuple[int, AnalysisMode]]:
        """Return all subscribers as ``[(chat_id, mode), ...]``."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chat_id, mode FROM briefing_subscribers ORDER BY subscribed_at"
            ).fetchall()
        return [(int(r["chat_id"]), r["mode"]) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM briefing_subscribers").fetchone()
        return int(n)

    # ------------------------------------------------------------------
    # Run-history CRUD — used by the scheduler to dedupe same-day runs.
    # ------------------------------------------------------------------

    def get_run(self, run_date: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM briefing_runs WHERE run_date = ?", (run_date,),
            ).fetchone()

    def start_run(self, run_date: str, subscribers: int) -> bool:
        """Mark a run started. Returns False if the date already has a row (skip)."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO briefing_runs "
                "(run_date, started_at, subscribers) VALUES (?, ?, ?)",
                (run_date, now, subscribers),
            )
            return cur.rowcount > 0

    def finish_run(self, run_date: str, succeeded: int, failed: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE briefing_runs SET finished_at = ?, succeeded = ?, failed = ? "
                "WHERE run_date = ?",
                (now, succeeded, failed, run_date),
            )
