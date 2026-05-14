#!/usr/bin/env python3
"""Private Data Ops — read-only MCP access to the Private DB (relationships.db).

Exposes three read-only tools to AI clients (Claude Desktop, Cursor, mcp-cli,
local Ollama agents):

- list_groups        All groups + member counts, newest-touched first.
- find_group         Case-insensitive substring match on group name.
- get_group_members  One group plus its members, joined to fellows.db for
                     names + emails (single round-trip; AI doesn't need to
                     chain to shared-data-ops for the common case).

v1 scope: groups only. The schema also carries `fellow_tags` and `fellow_notes`,
but users aren't yet writing those at scale (per 2026-05-14 review). Notes/tags
land when there's usage to support.

Transport: stdio (the MCP standard for desktop AI clients).
DB access: read-only SQLite URI (mode=ro) on both relationships.db and the
ATTACHed fellows.db. Even a buggy tool can't mutate either store.

Privacy posture (AC-MCP-A — see ../docs/_pna_triage.md):
This server *does* return Private DB rows (your groups and the fellows in them).
Per AC-MCP-A, cloud AI clients should require explicit per-call consent before
seeing this data. v1 does not implement that gate — it documents the boundary
and trusts the user's choice of MCP client. Wire it up to a local model
(Claude Desktop + local model, Cursor + Ollama) for the green-path posture.
The proper consent UX lands when the spec's typed contracts land.
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.fellows_queries import row_to_fellow  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

log = logging.getLogger("private-data-ops")

mcp = FastMCP("private-data-ops")

# Module-level paths; set by main() before mcp.run() starts the loop.
_REL_DB_PATH: Path | None = None
_FELLOWS_DB_PATH: Path | None = None

LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 500


def _path_to_ro_uri(p: Path) -> str:
    return f"file:{quote(str(p), safe='/:')}?mode=ro"


def _open_ro() -> sqlite3.Connection:
    """Open relationships.db RO with fellows.db ATTACHed as `f` RO.

    Read-only-ness is enforced at the SQLite level (mode=ro), not just by
    convention — accidental writes raise OperationalError.
    """
    if _REL_DB_PATH is None or _FELLOWS_DB_PATH is None:
        raise RuntimeError("DB paths not configured; call main() first")
    conn = sqlite3.connect(_path_to_ro_uri(_REL_DB_PATH), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("ATTACH DATABASE ? AS f", (_path_to_ro_uri(_FELLOWS_DB_PATH),))
    return conn


def _to_group_summary(row: sqlite3.Row) -> dict:
    """Shape for list/find responses — one row per group, no member list."""
    return {
        "group_id": row["id"],
        "name": row["name"],
        "note": row["note"],
        "member_count": row["member_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _to_member(row: sqlite3.Row) -> dict:
    """Shape for one member of a group — record_id from Private DB + display
    fields from fellows.db. ``contact_email`` is null when the fellow has no
    email or when the record_id no longer resolves in the Shared DB (orphan
    after a re-mirror, per AC-10 / SH-5).
    """
    return {
        "record_id": row["record_id"],
        "slug": row["slug"],
        "name": row["name"],
        "contact_email": row["contact_email"],
        "fellow_type": row["fellow_type"],
        "currently_based_in": row["currently_based_in"],
    }


@mcp.tool()
def list_groups(limit: int = LIST_LIMIT_DEFAULT) -> dict:
    """List all groups in the Private DB, newest-touched first.

    Args:
        limit: Max groups to return. Default 100, capped at 500.

    Returns:
        {
          "total": int,                 # total groups (pre-limit)
          "results": list[GroupSummary] # {group_id, name, note, member_count,
                                        #  created_at, updated_at}
        }
    """
    limit = max(1, min(int(limit), LIST_LIMIT_MAX))
    with _open_ro() as conn:
        total = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        cur = conn.execute(
            """
            SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                   COUNT(gm.fellow_record_id) AS member_count
            FROM groups g
            LEFT JOIN group_members gm ON gm.group_id = g.id
            GROUP BY g.id
            ORDER BY g.updated_at DESC, g.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        results = [_to_group_summary(r) for r in cur.fetchall()]
    log.debug("list_groups(limit=%d) -> total=%d, returned=%d", limit, total, len(results))
    return {"total": total, "results": results}


@mcp.tool()
def find_group(name: str, limit: int = LIST_LIMIT_DEFAULT) -> dict:
    """Find groups whose name contains the given substring (case-insensitive).

    Useful when the user asks for "the climate group" — match on substring,
    return whatever's there. If multiple match, the AI client can disambiguate
    by showing the names or by calling get_group_members on each.

    Args:
        name: Substring to match against group names. Empty string returns
            no results (use list_groups for that).
        limit: Max groups to return. Default 100, capped at 500.

    Returns:
        {
          "query": str,                 # echoed (trimmed) query
          "total": int,                 # matches pre-limit
          "results": list[GroupSummary] # same shape as list_groups.results
        }
    """
    q = (name or "").strip()
    if not q:
        return {"query": "", "total": 0, "results": []}
    limit = max(1, min(int(limit), LIST_LIMIT_MAX))
    pattern = f"%{q}%"
    with _open_ro() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM groups WHERE name LIKE ? COLLATE NOCASE",
            (pattern,),
        ).fetchone()[0]
        cur = conn.execute(
            """
            SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                   COUNT(gm.fellow_record_id) AS member_count
            FROM groups g
            LEFT JOIN group_members gm ON gm.group_id = g.id
            WHERE g.name LIKE ? COLLATE NOCASE
            GROUP BY g.id
            ORDER BY g.updated_at DESC, g.id DESC
            LIMIT ?
            """,
            (pattern, limit),
        )
        results = [_to_group_summary(r) for r in cur.fetchall()]
    log.debug("find_group(%r, limit=%d) -> total=%d, returned=%d", q, limit, total, len(results))
    return {"query": q, "total": total, "results": results}


@mcp.tool()
def get_group_members(group_id: int) -> dict | None:
    """Fetch one group plus its members, joined to fellows.db.

    Single round-trip — the AI doesn't need to chain to shared-data-ops to
    resolve names + emails for the common case (drafting an email to a group).
    Members with a ``record_id`` that no longer resolves in fellows.db come
    back with null ``name`` / ``contact_email`` (orphan after a Shared DB
    re-mirror — see AC-10).

    Args:
        group_id: The numeric group id from list_groups / find_group.

    Returns:
        {
          "group": GroupSummary,
          "members": list[Member]       # {record_id, slug, name,
                                        #  contact_email, fellow_type,
                                        #  currently_based_in}
        }
        or null if no group with that id exists.
    """
    gid = int(group_id)
    with _open_ro() as conn:
        row = conn.execute(
            """
            SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                   (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id)
                       AS member_count
            FROM groups g
            WHERE g.id = ?
            """,
            (gid,),
        ).fetchone()
        if row is None:
            return None
        group = _to_group_summary(row)
        members_cur = conn.execute(
            """
            SELECT gm.fellow_record_id AS record_id,
                   fl.slug AS slug,
                   fl.name AS name,
                   fl.contact_email AS contact_email,
                   fl.fellow_type AS fellow_type,
                   fl.currently_based_in AS currently_based_in
            FROM group_members gm
            LEFT JOIN f.fellows fl ON fl.record_id = gm.fellow_record_id
            WHERE gm.group_id = ?
            ORDER BY COALESCE(fl.name, gm.fellow_record_id) ASC
            """,
            (gid,),
        )
        members = [_to_member(r) for r in members_cur.fetchall()]
    log.debug("get_group_members(%d) -> %d members", gid, len(members))
    return {"group": group, "members": members}


def _resolve_db_paths(rel_arg: str | None, fellows_arg: str | None) -> tuple[Path, Path]:
    if rel_arg:
        rel = Path(rel_arg).resolve()
    else:
        env = os.environ.get("FELLOWS_RELATIONSHIPS_DB_PATH")
        rel = Path(env).resolve() if env else (REPO_ROOT / "app" / "relationships.db").resolve()
    if fellows_arg:
        fel = Path(fellows_arg).resolve()
    else:
        env = os.environ.get("FELLOWS_DB_PATH")
        fel = Path(env).resolve() if env else (REPO_ROOT / "app" / "fellows.db").resolve()
    return rel, fel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private Data Ops MCP server for relationships.db.")
    parser.add_argument(
        "--db", default=None,
        help="Path to relationships.db. Defaults to FELLOWS_RELATIONSHIPS_DB_PATH or <repo>/app/relationships.db.",
    )
    parser.add_argument(
        "--fellows-db", default=None,
        help="Path to fellows.db. Defaults to FELLOWS_DB_PATH or <repo>/app/fellows.db.",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Log tool calls and resolved args to stderr.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    global _REL_DB_PATH, _FELLOWS_DB_PATH
    _REL_DB_PATH, _FELLOWS_DB_PATH = _resolve_db_paths(args.db, args.fellows_db)
    if not _REL_DB_PATH.is_file():
        print(f"relationships.db not found at {_REL_DB_PATH}", file=sys.stderr)
        print("Open the app once to bootstrap it, or download a backup from", file=sys.stderr)
        print("Settings → Restore from backup and place it at the path above.", file=sys.stderr)
        return 1
    if not _FELLOWS_DB_PATH.is_file():
        print(f"fellows.db not found at {_FELLOWS_DB_PATH}", file=sys.stderr)
        print("Run: just db-rebuild", file=sys.stderr)
        return 1
    try:
        with _open_ro() as conn:
            conn.execute("SELECT 1 FROM groups LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM f.fellows LIMIT 1").fetchone()
    except sqlite3.Error as e:
        print(f"Cannot open Private/Shared DBs read-only: {e}", file=sys.stderr)
        return 1

    log.info(
        "private-data-ops MCP server starting; rel_db=%s fellows_db=%s",
        _REL_DB_PATH, _FELLOWS_DB_PATH,
    )
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
