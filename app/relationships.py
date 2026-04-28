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

import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

APP_DIR = Path(__file__).resolve().parent
# Default location. Tests override via FELLOWS_RELATIONSHIPS_DB_PATH so they
# don't pollute the dev DB; the env var is resolved per-call (see open_db).
RELATIONSHIPS_DB_PATH = APP_DIR / "relationships.db"
FELLOWS_DB_PATH = APP_DIR / "fellows.db"


def resolve_relationships_db_path() -> Path:
    """Return the relationships.db path, honouring FELLOWS_RELATIONSHIPS_DB_PATH."""
    env = os.environ.get("FELLOWS_RELATIONSHIPS_DB_PATH")
    if env:
        return Path(env)
    return RELATIONSHIPS_DB_PATH

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


def _now_iso() -> str:
    """ISO-8601 timestamp with seconds precision (UTC)."""
    import datetime

    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def list_groups(conn: sqlite3.Connection) -> list[dict]:
    """All groups + member counts, newest-touched first."""
    cur = conn.execute(
        """
        SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
               COUNT(gm.fellow_record_id) AS count
        FROM groups g
        LEFT JOIN group_members gm ON gm.group_id = g.id
        GROUP BY g.id
        ORDER BY g.updated_at DESC, g.id DESC
        """
    )
    return [dict(r) for r in cur.fetchall()]


def get_group(
    conn: sqlite3.Connection,
    group_id: int,
    *,
    attached: bool = True,
) -> dict | None:
    """One group with its members, or None if not found.

    ``attached``: when True, JOIN against ATTACHed ``f.fellows`` so each
    member carries the fellow's display name. When False (PWA path,
    where we skip ATTACH on OPFS), members come back with ``record_id``
    only and the caller resolves names client-side from the in-memory
    fellows cache.
    """
    row = conn.execute(
        "SELECT * FROM groups WHERE id = ?", (group_id,)
    ).fetchone()
    if row is None:
        return None
    out = dict(row)
    if attached:
        members = conn.execute(
            """
            SELECT gm.fellow_record_id AS record_id, fl.name AS name
            FROM group_members gm
            LEFT JOIN f.fellows fl ON fl.record_id = gm.fellow_record_id
            WHERE gm.group_id = ?
            ORDER BY COALESCE(fl.name, gm.fellow_record_id) ASC
            """,
            (group_id,),
        ).fetchall()
    else:
        members = conn.execute(
            """
            SELECT fellow_record_id AS record_id
            FROM group_members
            WHERE group_id = ?
            ORDER BY fellow_record_id ASC
            """,
            (group_id,),
        ).fetchall()
    out["members"] = [dict(m) for m in members]
    return out


def _dedupe_record_ids(ids):
    """Strip empty / whitespace-only / duplicate record_ids, preserving order."""
    seen = set()
    out = []
    for rid in ids or ():
        if not isinstance(rid, str):
            continue
        s = rid.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def create_group(
    conn: sqlite3.Connection,
    *,
    name: str,
    note: str = "",
    fellow_record_ids=None,
) -> int:
    """Insert a group and link its members in one transaction. Returns the new id."""
    now = _now_iso()
    cur = conn.execute(
        "INSERT INTO groups(name, note, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name, note, now, now),
    )
    group_id = cur.lastrowid
    rows = [(group_id, rid) for rid in _dedupe_record_ids(fellow_record_ids)]
    if rows:
        conn.executemany(
            "INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)",
            rows,
        )
    conn.commit()
    return group_id


def update_group(
    conn: sqlite3.Connection,
    group_id: int,
    *,
    name=None,
    note=None,
    fellow_record_ids=None,
) -> bool:
    """Patch a group. Each field is optional. ``fellow_record_ids``, when
    provided, is a full replacement of group_members for this group.
    Returns True if the group existed (and was patched), False if not found.
    """
    exists = conn.execute(
        "SELECT 1 FROM groups WHERE id = ?", (group_id,)
    ).fetchone()
    if not exists:
        return False
    sets = ["updated_at = ?"]
    params = [_now_iso()]
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if note is not None:
        sets.append("note = ?")
        params.append(note)
    params.append(group_id)
    conn.execute(f"UPDATE groups SET {', '.join(sets)} WHERE id = ?", params)
    if fellow_record_ids is not None:
        conn.execute(
            "DELETE FROM group_members WHERE group_id = ?", (group_id,)
        )
        rows = [(group_id, rid) for rid in _dedupe_record_ids(fellow_record_ids)]
        if rows:
            conn.executemany(
                "INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)",
                rows,
            )
    conn.commit()
    return True


def delete_group(conn: sqlite3.Connection, group_id: int) -> bool:
    """Delete a group (FK cascades to group_members). Returns True if a row was removed."""
    cur = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    return cur.rowcount > 0


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
    rel = rel_db_path or resolve_relationships_db_path()
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
