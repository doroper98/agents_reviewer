"""IV 스큐 일별 캐시 단위 테스트 — v7.9.11. 순수 SQLite (네트워크 없음)."""

import os
import tempfile

from src.tools.skew_cache import store_skew, recent_skew


def _pts():
    return [
        {"strike": 350.0, "iv": 70.0, "type": "put"},
        {"strike": 355.0, "iv": 68.0, "type": "call"},
    ]


def test_store_and_recent_roundtrip():
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    for dt in ("2026-06-15", "2026-06-16", "2026-06-17"):
        assert store_skew(path, dt, "202607", _pts())
    hist = recent_skew(path, "202607", 10, "2026-06-17")
    assert len({h["date"] for h in hist}) == 3
    assert len(hist) == 6
    assert all({"date", "type", "strike", "iv"} <= set(h) for h in hist)


def test_store_idempotent_overwrite():
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    store_skew(path, "2026-06-17", "202607", _pts())
    store_skew(path, "2026-06-17", "202607", [{"strike": 350.0, "iv": 71.0, "type": "put"}])
    hist = recent_skew(path, "202607", 10, "2026-06-17")
    put = [h["iv"] for h in hist if h["type"] == "put" and h["strike"] == 350.0]
    assert put == [71.0]  # 덮어쓰기 (중복 행 없음)


def test_recent_limits_to_n_dates():
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    for dt in ("2026-06-13", "2026-06-16", "2026-06-17"):
        store_skew(path, dt, "202607", _pts())
    hist = recent_skew(path, "202607", 2, "2026-06-17")
    assert sorted({h["date"] for h in hist}) == ["2026-06-16", "2026-06-17"]


def test_recent_unknown_expiry_graceful():
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    store_skew(path, "2026-06-17", "202607", _pts())
    assert recent_skew(path, "202609", 10, "2026-06-17") == []


def test_store_empty_graceful():
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    assert store_skew(path, "2026-06-17", "202607", []) is False


def test_premium_roundtrip_and_legacy_null():
    """v8.2.5 — premium 컬럼 저장/조회 + 미적재(구 캐시)분은 None."""
    path = os.path.join(tempfile.mkdtemp(), "iv.sqlite")
    # premium 있는 점 + 없는 점
    store_skew(path, "2026-06-17", "202607", [
        {"strike": 350.0, "iv": 70.0, "type": "put", "premium": 12.5},
        {"strike": 355.0, "iv": 68.0, "type": "call"},  # premium 누락
    ])
    hist = recent_skew(path, "202607", 10, "2026-06-17")
    assert all("premium" in h for h in hist)
    put = next(h for h in hist if h["type"] == "put")
    call = next(h for h in hist if h["type"] == "call")
    assert put["premium"] == 12.5
    assert call["premium"] is None
