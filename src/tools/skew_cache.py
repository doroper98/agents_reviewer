"""IV 스큐 일별 캐시 (멱등 append) — 지난 N영업일 스큐 오버레이용. v7.9.11.

장마감 브리핑마다 그날 front-expiry 옵션 체인의 (strike, type, iv) 를 저장하고,
차트 빌드 시 최근 N영업일을 읽어 '오늘=진하게, 과거=옅게' 페이드 오버레이를 만든다.
breadth_fetcher 캐시와 동일 패턴 — 과거일은 재수집 않고 append, 순수 SQLite.

CLI 없음 (derivatives_fetcher 의 backfill 이 이 모듈을 호출해 채운다).
"""

from __future__ import annotations

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def _connect(path: str) -> sqlite3.Connection | None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS skew ("
            "date TEXT NOT NULL, expiry TEXT NOT NULL, opt_type TEXT NOT NULL, "
            "strike REAL NOT NULL, iv REAL NOT NULL, "
            "PRIMARY KEY (date, expiry, opt_type, strike))"
        )
        # v8.2.5 — 옵션 가격(프리미엄) 컬럼. 구 캐시(없는 경우)엔 추가만 (nullable —
        # 마이그레이션 전 적재분은 premium NULL, 가격 패널은 graceful skip).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(skew)").fetchall()]
        if "premium" not in cols:
            conn.execute("ALTER TABLE skew ADD COLUMN premium REAL")
        conn.commit()
        return conn
    except Exception as e:  # pragma: no cover — 디스크/권한 문제는 graceful
        logger.warning("[skew_cache] connect 실패 (%s): %s", path, e)
        return None


def store_skew(path: str, date: str, expiry: str, points: list[dict]) -> bool:
    """그날 스큐 점들을 저장 (idempotent — 같은 (date,expiry,type,strike) 는 덮어씀).

    points: [{strike, iv, type, premium?}] (iv 는 % 단위, type 은 'put'|'call',
    premium 은 옵션 가격 — 없으면 NULL 로 저장, v8.2.5).
    """
    if not date or not expiry or not points:
        return False
    conn = _connect(path)
    if conn is None:
        return False
    try:
        rows = []
        for p in points:
            try:
                prem = p.get("premium")
                prem_val = None if prem is None else float(prem)
                rows.append((
                    date, expiry, str(p["type"]), float(p["strike"]),
                    float(p["iv"]), prem_val,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        if not rows:
            return False
        conn.executemany(
            "INSERT OR REPLACE INTO skew(date,expiry,opt_type,strike,iv,premium) "
            "VALUES(?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        return True
    except Exception as e:  # pragma: no cover
        logger.warning("[skew_cache] store 실패: %s", e)
        return False
    finally:
        conn.close()


def recent_skew(path: str, expiry: str, n_dates: int, as_of: str) -> list[dict]:
    """as_of 이하 최근 n_dates 영업일의 스큐 점들.
    [{date, type, strike, iv, premium}] 오름차순 (premium 은 미적재분이면 None).

    데이터 없으면 빈 리스트 (graceful — 차트는 오늘만 그린다).
    """
    if not expiry or n_dates < 1:
        return []
    conn = _connect(path)
    if conn is None:
        return []
    try:
        cur = conn.execute(
            "SELECT DISTINCT date FROM skew WHERE expiry=? AND date<=? "
            "ORDER BY date DESC LIMIT ?",
            (expiry, as_of, int(n_dates)),
        )
        dates = [r[0] for r in cur.fetchall()]
        if not dates:
            return []
        placeholders = ",".join("?" * len(dates))
        cur = conn.execute(
            "SELECT date,opt_type,strike,iv,premium FROM skew "
            f"WHERE expiry=? AND date IN ({placeholders}) ORDER BY date ASC, strike ASC",
            (expiry, *dates),
        )
        return [
            {"date": r[0], "type": r[1], "strike": r[2], "iv": r[3], "premium": r[4]}
            for r in cur.fetchall()
        ]
    except Exception as e:  # pragma: no cover
        logger.warning("[skew_cache] recent 실패: %s", e)
        return []
    finally:
        conn.close()
