"""WatchlistRegistry — SQLite CRUD for WatchSignal persistence.

V3 Step 5-B (v2.9.5). Standard library only (sqlite3) — 의존성 추가 0.

Sync API on top of sqlite3 — sqlite3 자체가 fast (≤ ms 수준) 라 asyncio event loop 차단 영향
무시 가능. 동기 함수를 그대로 async 컨텍스트에서 호출.

Anti-pattern #11 회피: 본 registry 가 SSOT. ``ScenarioAnalysis.watch_signals`` (dict 배열) 은
``orchestrator`` 단계에서 ``convert_watch_signals()`` 로 변환되어 ``register()`` 됨.
"""

from __future__ import annotations

import json
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
            # v5.1.1: 기존 DB 에 chain_depth 컬럼이 없으면 idempotent 마이그레이션.
            # SQLite 는 ADD COLUMN IF NOT EXISTS 미지원 → PRAGMA 로 체크.
            existing_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(watchsignals)").fetchall()
            }
            if "chain_depth" not in existing_cols:
                conn.execute(
                    "ALTER TABLE watchsignals ADD COLUMN chain_depth INTEGER NOT NULL DEFAULT 0"
                )
                logger.info("[watchlist] Migrated: added chain_depth column to watchsignals")
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
                 parent_chat_id, fired, fired_at, created_at, chain_depth)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id, signal.description, signal.measurement,
                    signal.direction, signal.deadline, signal.follow_up_action,
                    signal.parent_report_url, signal.parent_report_id,
                    signal.parent_chat_id,
                    int(signal.fired), signal.fired_at, created_at,
                    int(signal.chain_depth),
                ),
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # v5.1.1 — Report metadata (자동 후속 보고서용)
    # ------------------------------------------------------------------

    def register_report_meta(
        self,
        report_id: str,
        event_description: str,
        scenarios: list[dict],
        chain_depth: int = 0,
    ) -> bool:
        """보고서의 부모 맥락 메타 등록 — 신호 발화 시 ParentContext 즉시 조립용.

        report_id 가 비어있으면 no-op. 동일 ID 재등록은 REPLACE (재배포 케이스 흡수).
        """
        if not report_id:
            return False
        created_at = datetime.utcnow().isoformat()
        try:
            scenarios_json = json.dumps(scenarios or [], ensure_ascii=False)
        except (TypeError, ValueError):
            scenarios_json = "[]"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO report_meta
                (report_id, event_description, scenarios_json, chain_depth, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_id, event_description, scenarios_json, int(chain_depth), created_at),
            )
        return True

    def get_report_meta(self, report_id: str) -> dict | None:
        """report_id 로 부모 메타 조회. 반환 dict: {event_description, scenarios, chain_depth}."""
        if not report_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_meta WHERE report_id = ?", (report_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            scenarios = json.loads(row["scenarios_json"] or "[]")
        except (TypeError, ValueError):
            scenarios = []
        return {
            "event_description": row["event_description"] or "",
            "scenarios": scenarios if isinstance(scenarios, list) else [],
            "chain_depth": int(row["chain_depth"] or 0),
        }

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
    # v5.1.1: chain_depth 는 마이그레이션 전 row 에 없을 수 있어 안전 접근.
    try:
        depth_val = row["chain_depth"]
    except (IndexError, KeyError):
        depth_val = 0
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
        chain_depth=int(depth_val or 0),
    )
