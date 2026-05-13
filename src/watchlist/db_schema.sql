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
    created_at         TEXT    NOT NULL,                    -- ISO 8601 datetime
    chain_depth        INTEGER NOT NULL DEFAULT 0           -- v5.1.1: 0=부모, 1=자식. 2 이상은 자동 후속 차단
);

CREATE INDEX IF NOT EXISTS idx_watchsignals_active   ON watchsignals(fired, deadline);
CREATE INDEX IF NOT EXISTS idx_watchsignals_chat     ON watchsignals(parent_chat_id, fired);
CREATE INDEX IF NOT EXISTS idx_watchsignals_deadline ON watchsignals(deadline);

-- v5.1.1: 부모 보고서 메타 — 신호 발화 시 ParentContext 즉시 조립용.
-- event_description + scenarios JSON 영구 보관. 자동 후속 체인 차단 판단에도 사용.
CREATE TABLE IF NOT EXISTS report_meta (
    report_id          TEXT    PRIMARY KEY,
    event_description  TEXT    NOT NULL DEFAULT '',
    scenarios_json     TEXT    NOT NULL DEFAULT '[]',
    chain_depth        INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT    NOT NULL
);
