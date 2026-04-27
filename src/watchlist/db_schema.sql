-- Watchlist Registry SQLite schema — V3 Step 5-B (v2.9.5).
-- Anti-pattern #11 회피: WatchSignal 은 보고서 텍스트로만 남지 않고 본 테이블에 영구 저장.

CREATE TABLE IF NOT EXISTS watchsignals (
    signal_id          TEXT    PRIMARY KEY,
    description        TEXT    NOT NULL,
    measurement        TEXT    NOT NULL DEFAULT '',
    direction          TEXT    NOT NULL CHECK (direction IN ('confirms_base', 'rejects_base', 'ambiguous')),
    deadline           TEXT    NOT NULL,                    -- ISO 8601 date "YYYY-MM-DD"
    follow_up_action   TEXT    NOT NULL DEFAULT '',
    parent_report_url  TEXT    NOT NULL DEFAULT '',
    parent_report_id   TEXT    NOT NULL DEFAULT '',
    parent_chat_id     INTEGER NOT NULL DEFAULT 0,
    fired              INTEGER NOT NULL DEFAULT 0,          -- 0=active, 1=fired
    fired_at           TEXT,                                -- ISO 8601 datetime; NULL 이면 미발화
    created_at         TEXT    NOT NULL                     -- ISO 8601 datetime
);

CREATE INDEX IF NOT EXISTS idx_watchsignals_active   ON watchsignals(fired, deadline);
CREATE INDEX IF NOT EXISTS idx_watchsignals_chat     ON watchsignals(parent_chat_id, fired);
CREATE INDEX IF NOT EXISTS idx_watchsignals_deadline ON watchsignals(deadline);
