"""User-data store for the EHF Fellows app.

Lives in ``app/relationships.db``, a separate SQLite file from
``app/fellows.db``:

- ``fellows.db`` holds imported Knack/EHF contact data — read-only at
  runtime, replaced on every PWA update.
- ``relationships.db`` holds user-authored data (groups, tags, notes,
  settings) — read-write, persists across app updates.

Tables here join to ``fellows`` via SQLite ``ATTACH DATABASE`` in
read-only mode (see ``open_db``). The same architecture works in the
PWA (sqlite3.wasm + OPFS) as it does on the dev server; the JS schema
mirror lives in ``app/static/app.js`` near ``RELATIONSHIPS_SCHEMA_SQL``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

APP_DIR = Path(__file__).resolve().parent
RELATIONSHIPS_DB_PATH = APP_DIR / "relationships.db"
FELLOWS_DB_PATH = APP_DIR / "fellows.db"

# Bump when the schema below changes. Stored in PRAGMA user_version on
# every bootstrap so we can branch on it for future migrations.
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    fellow_record_id TEXT NOT NULL,
    PRIMARY KEY (group_id, fellow_record_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_group
    ON group_members(group_id);

-- Reserved for a later PR (tag/note CRUD UI). Schema lives here from PR 1
-- so cross-DB joins are designed in once.
CREATE TABLE IF NOT EXISTS fellow_tags (
    fellow_record_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (fellow_record_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_fellow_tags_tag
    ON fellow_tags(tag);

CREATE TABLE IF NOT EXISTS fellow_notes (
    fellow_record_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Single key/value bag for user prefs (e.g. ``self_email`` override).
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _path_to_sqlite_uri(p: Path, *, mode: str = "rwc") -> str:
    """Build a ``file:``-style URI SQLite understands. URL-quotes path bytes."""
    quoted = quote(str(p), safe="/:")
    return f"file:{quoted}?mode={mode}"


def bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes if missing. Idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def open_db(
    *,
    rel_db_path: Path | None = None,
    fellows_db_path: Path | None = None,
    attach_fellows: bool = True,
) -> sqlite3.Connection:
    """Open ``relationships.db`` (creating + bootstrapping if needed).

    When ``attach_fellows`` is True, ``fellows.db`` is ATTACHed as ``f`` in
    read-only mode (``?mode=ro``). Any accidental write to ``f.*`` raises
    ``sqlite3.OperationalError`` — the read-only-ness of contact data is
    enforced at the SQLite level, not just the app layer.
    """
    rel = rel_db_path or RELATIONSHIPS_DB_PATH
    fel = fellows_db_path or FELLOWS_DB_PATH
    rel.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_path_to_sqlite_uri(rel, mode="rwc"), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    bootstrap_schema(conn)
    if attach_fellows:
        if not fel.is_file():
            raise FileNotFoundError(f"fellows.db not found at {fel}")
        conn.execute(
            "ATTACH DATABASE ? AS f",
            (_path_to_sqlite_uri(fel, mode="ro"),),
        )
    return conn
