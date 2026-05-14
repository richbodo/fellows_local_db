-- Private schema interface — canonical SQL DDL for a conforming Private DB.
--
-- Sub-contracts PR-1 through PR-5 from `_pna_triage.md` Part 4. The Private DB
-- holds user-authored relationship data (groups, tags, notes, settings,
-- optional comms history); it is read-write from the workspace and is the
-- store that AC-1 promises to keep local-only.
--
-- This DDL is the spec-generic shape. Implementations may rename for
-- ergonomics (fellows_local_db calls record-keyed tables `fellow_*` and uses
-- a simpler `settings(key, value)` without the workspace partition); the
-- spec-target shape is below.
--
-- PRAGMAs that MUST run per connection (PR-3):
--   PRAGMA foreign_keys = ON;
--   PRAGMA user_version = <SCHEMA_VERSION>;   -- bumped on schema migrations
--
-- Idempotency note (PR-5): every CREATE below uses `IF NOT EXISTS` so a
-- restore from an older backup gains any newer tables on next boot without
-- a manual migration step. The same bootstrap script runs on cold-start and
-- on restore.

-- PR-1: groups — user-curated subsets of Shared DB records.
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,                  -- ISO-8601
    updated_at  TEXT NOT NULL                   -- ISO-8601; drives list ordering
);

-- PR-1: group_members — joins a group to Shared DB records via record_id.
-- ON DELETE CASCADE ensures deleting a group removes its members (PRAGMA
-- foreign_keys=ON is required per PR-3 or the cascade is silently inert).
--
-- fellows_local_db naming: this column is `fellow_record_id` in the live
-- schema; the spec-generic column name is `record_id`. The shape and PK
-- semantics are identical.
CREATE TABLE IF NOT EXISTS group_members (
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    record_id   TEXT NOT NULL,
    PRIMARY KEY (group_id, record_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);

-- PR-1: record_tags — per-record tags. fellows_local_db naming: `fellow_tags`
-- with `fellow_record_id`.
CREATE TABLE IF NOT EXISTS record_tags (
    record_id   TEXT NOT NULL,
    tag         TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (record_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_record_tags_tag ON record_tags(tag);

-- PR-1: record_notes — per-record freeform notes. fellows_local_db naming:
-- `fellow_notes` with `fellow_record_id`.
CREATE TABLE IF NOT EXISTS record_notes (
    record_id   TEXT PRIMARY KEY,
    body        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- PR-1: settings — key/value bag partitioned by workspace_id.
--
-- Single-workspace PNAs use the empty string as workspace_id (default).
-- Multi-workspace PNAs (per the "one origin, many workspaces" decision in
-- _pna_triage.md Part 3) use their workspace's id so each workspace has
-- its own settings namespace.
--
-- fellows_local_db is single-workspace today and uses a simpler
-- `settings(key TEXT PRIMARY KEY, value TEXT)` table — the spec-generic
-- composite-PK shape below is the forward-compatible target. A schema
-- migration can extend the existing settings table by adding workspace_id
-- with a default of '' to preserve all existing rows.
CREATE TABLE IF NOT EXISTS settings (
    workspace_id    TEXT NOT NULL DEFAULT '',
    key             TEXT NOT NULL,
    value           TEXT,
    PRIMARY KEY (workspace_id, key)
);

-- PR-2: record_comms_history — opt-in log of outreach launched from the
-- workspace.
--
-- **Disabled by default.** The workspace MUST NOT write to this table
-- unless `settings.value WHERE workspace_id='' AND key='comms_history_enabled'`
-- is the literal string '1'. The user has full read / edit / delete
-- control over the rows; they live in the Private DB and are protected by
-- AC-1 (never leave the device).
--
-- `transport` records which Communications transport launched the outreach
-- (e.g., 'mailto', 'signal'). `direction` is 'outbound' for messages the
-- user sent and 'inbound' for messages the user manually logs as received.
-- `summary` is user-editable shorthand; the message body itself is NOT
-- stored — that's the responsibility of the user's mail/messaging client.
CREATE TABLE IF NOT EXISTS record_comms_history (
    id          INTEGER PRIMARY KEY,
    record_id   TEXT NOT NULL,
    transport   TEXT NOT NULL,                  -- e.g., 'mailto', 'signal'
    direction   TEXT NOT NULL,                  -- 'outbound' | 'inbound'
    occurred_at TEXT NOT NULL,                  -- ISO-8601
    summary     TEXT NOT NULL DEFAULT ''        -- user-editable shorthand
);

CREATE INDEX IF NOT EXISTS idx_record_comms_history_record
    ON record_comms_history(record_id);

-- PR-4 (durability) and PR-5 (backup/restore conformance) are operational
-- properties, not table shapes. They appear in this contract as comments:
--
-- PR-4: The Private DB is never replaced on app update. It survives Clear
-- App Cache. It is wiped only by Reset Everything (the workspace's
-- explicit-user-choice nuclear path; ST-10 implements the wipe in browser
-- PNAs).
--
-- PR-5: Auto-backups + user-supplied restores are part of the Storage
-- slot's contract (ST-6, ST-7). This DDL is idempotent so a restore from
-- an older backup gains any newer tables on next boot without a manual
-- migration step. Schema migrations beyond CREATE-IF-NOT-EXISTS will
-- branch on `PRAGMA user_version`.
