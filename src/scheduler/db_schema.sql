-- Scheduler / Daily Briefing subscriptions schema — v5.1.0.
-- 별도 .db 파일 (scheduler.db) — watchlist 와 분리해 관심사 격리.

CREATE TABLE IF NOT EXISTS briefing_subscribers (
    chat_id        INTEGER PRIMARY KEY,
    subscribed_at  TEXT    NOT NULL,                       -- ISO 8601 datetime (UTC)
    mode           TEXT    NOT NULL DEFAULT 'deep'
        CHECK (mode IN ('fast', 'standard', 'deep'))
);

CREATE INDEX IF NOT EXISTS idx_briefing_mode ON briefing_subscribers(mode);

-- 마지막 트리거 시각 기록 — 봇 재시작 직후 같은 날 중복 트리거 방지에 사용.
CREATE TABLE IF NOT EXISTS briefing_runs (
    run_date    TEXT    PRIMARY KEY,        -- 'YYYY-MM-DD' in DAILY_BRIEFING_TZ
    started_at  TEXT    NOT NULL,           -- ISO 8601 datetime (UTC)
    finished_at TEXT,                       -- ISO 8601 datetime (UTC); NULL 이면 진행 중/실패
    subscribers INTEGER NOT NULL DEFAULT 0,
    succeeded   INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0
);
