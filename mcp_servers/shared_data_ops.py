#!/usr/bin/env python3
"""Shared Data Ops — read-only MCP access to the Shared DB (fellows.db).

Exposes four read-only tools to AI clients (Claude Desktop, Cursor, mcp-cli,
local Ollama agents):

- search_fellows      FTS5 full-text search.
- get_fellow          Single record by slug or record_id, full shape.
- list_fellows        Structured-filter list with cursor pagination.
- get_directory_stats Aggregates for "what's in this directory" questions.

Transport: stdio (the MCP standard for desktop AI clients).
DB access: read-only SQLite URI (mode=ro) — even a buggy tool can't mutate.
Storage scope: the Shared DB only (fellows.db). The Private DB
(relationships.db) is OPFS-owned by the workspace's dedicated worker and
out of scope here — that's the future Private Data Ops server's job. See
plans/local_first_worker_architecture.md and mcp_servers/README.md.
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

# Put the repo root on sys.path so we can reuse app/fellows_queries.py.
# Done before any local imports; the official `mcp` SDK is unaffected
# (this directory is named mcp_servers/, not mcp/, to avoid that collision).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.fellows_queries import (  # noqa: E402
    get_db_readonly,
    get_all_fellows,
    get_fellow_by_slug_or_id,
    search_fellows as _search_fellows,
    get_stats,
    row_to_fellow,
)

from mcp.server.fastmcp import FastMCP  # noqa: E402

log = logging.getLogger("shared-data-ops")

mcp = FastMCP("shared-data-ops")

# Module-level DB path; set by main() before mcp.run() starts the loop.
_DB_PATH: Path | None = None

SEARCH_LIMIT_DEFAULT = 25
SEARCH_LIMIT_MAX = 100
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 100


def _conn():
    """Open a fresh read-only connection. Cheap (SQLite); avoids cross-tool state."""
    if _DB_PATH is None:
        raise RuntimeError("DB path not configured; call main() first")
    return get_db_readonly(_DB_PATH)


def _to_summary(fellow: dict) -> dict:
    """Trim a full record to the SummaryFellow shape used by list/search responses.

    Keeps responses small enough that a 50-row list stays well under 10K tokens,
    while still carrying enough context for the LLM to decide whether to drill in.
    """
    return {
        "record_id": fellow.get("record_id"),
        "slug": fellow.get("slug"),
        "name": fellow.get("name"),
        "fellow_type": fellow.get("fellow_type"),
        "cohort": fellow.get("cohort"),
        "currently_based_in": fellow.get("currently_based_in"),
        "bio_tagline": fellow.get("bio_tagline"),
        "has_contact_email": bool(fellow.get("contact_email")),
    }


@mcp.tool()
def search_fellows(query: str, limit: int = SEARCH_LIMIT_DEFAULT) -> dict:
    """Full-text search across name, bio, cohort, fellow type, search tags, and key links.

    Uses SQLite FTS5. Pass natural keywords; FTS5 also accepts operators like
    "climate OR healthcare" and prefix matches like "auck*".

    Args:
        query: Search keywords. Must be non-empty.
        limit: Max results to return. Default 25, capped at 100.

    Returns:
        {
          "query": str,                    # the actual query that ran
          "total": int,                    # results before limit was applied
          "results": list[SummaryFellow],  # trimmed-row records
        }
    """
    q = (query or "").strip()
    if not q:
        return {"query": "", "total": 0, "results": []}
    limit = max(1, min(int(limit), SEARCH_LIMIT_MAX))
    with _conn() as conn:
        rows = _search_fellows(conn, q)
    total = len(rows)
    results = [_to_summary(r) for r in rows[:limit]]
    log.debug("search_fellows(%r, limit=%d) -> %d total, %d returned", q, limit, total, len(results))
    return {"query": q, "total": total, "results": results}


@mcp.tool()
def get_fellow(id: str) -> dict | None:
    """Fetch one fellow's full record by slug or record_id.

    Returns the full shape — all DB columns plus extra_json fields merged
    (ventures, career_highlights, mobile_number, skills_to_give, etc.).

    Args:
        id: A fellow's `slug` (e.g. "jane-doe") or `record_id`.

    Returns:
        The full fellow object, or null if no such record exists.
    """
    key = (id or "").strip()
    if not key:
        return None
    with _conn() as conn:
        return get_fellow_by_slug_or_id(conn, key)


@mcp.tool()
def list_fellows(
    fellow_type: str | None = None,
    cohort: str | None = None,
    region: str | None = None,
    primary_citizenship: str | None = None,
    has_contact_email: bool | None = None,
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
) -> dict:
    """List fellows by structured filters (use search_fellows for full-text).

    Filters AND together. The `region` filter matches against
    `global_regions_currently_based_in`, which is comma-separated, so a
    fellow in "Asia Pacific, Americas" matches either value.

    Args:
        fellow_type: Exact match on `fellow_type`.
        cohort: Exact match on `cohort`.
        region: Substring-match against `global_regions_currently_based_in`.
        primary_citizenship: Exact match on `primary_citizenship`.
        has_contact_email: True for fellows with a contact email; False for
            those without; None for no filter.
        limit: Max results to return. Default 50, capped at 100.
        offset: Number of results to skip before returning (for pagination).

    Returns:
        {
          "total": int,                   # total matching the filters (pre-limit)
          "offset": int,
          "limit": int,
          "filters_applied": dict,        # echo of the active filters
          "results": list[SummaryFellow],
        }
    """
    limit = max(1, min(int(limit), LIST_LIMIT_MAX))
    offset = max(0, int(offset))
    where = []
    params: list = []
    if fellow_type:
        where.append("fellow_type = ?")
        params.append(fellow_type)
    if cohort:
        where.append("cohort = ?")
        params.append(cohort)
    if region:
        where.append("global_regions_currently_based_in LIKE ?")
        params.append(f"%{region}%")
    if primary_citizenship:
        where.append("primary_citizenship = ?")
        params.append(primary_citizenship)
    if has_contact_email is True:
        where.append("contact_email IS NOT NULL AND contact_email != ''")
    elif has_contact_email is False:
        where.append("(contact_email IS NULL OR contact_email = '')")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    with _conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM fellows{where_sql}",
            params,
        ).fetchone()[0]
        cur = conn.execute(
            f"SELECT * FROM fellows{where_sql} ORDER BY name ASC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = [row_to_fellow(r) for r in cur.fetchall()]
    results = [_to_summary(r) for r in rows]
    filters_applied = {
        "fellow_type": fellow_type,
        "cohort": cohort,
        "region": region,
        "primary_citizenship": primary_citizenship,
        "has_contact_email": has_contact_email,
    }
    filters_applied = {k: v for k, v in filters_applied.items() if v is not None}
    log.debug("list_fellows filters=%r -> total=%d, returned=%d", filters_applied, total, len(results))
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters_applied": filters_applied,
        "results": results,
    }


@mcp.tool()
def get_directory_stats() -> dict:
    """Aggregate statistics for "what's in this directory" questions.

    Same shape as the dev HTTP server's `GET /api/stats` response:
    total count, breakdowns by fellow type / cohort / region, plus
    field-completeness counts (how many fellows have a non-empty value
    for each column or extra_json key).

    Returns:
        {
          "total": int,
          "by_fellow_type": list[{"label": str, "count": int}],
          "by_cohort":      list[{"label": str, "count": int}],
          "by_region":      list[{"label": str, "count": int}],
          "field_completeness": list[{"label": str, "count": int}],
        }
    """
    with _conn() as conn:
        return get_stats(conn)


def _resolve_db_path(cli_arg: str | None) -> Path:
    if cli_arg:
        return Path(cli_arg).resolve()
    env = os.environ.get("FELLOWS_DB_PATH")
    if env:
        return Path(env).resolve()
    return (REPO_ROOT / "app" / "fellows.db").resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shared-only Data Ops MCP server for fellows.db.")
    parser.add_argument("--db", default=None,
                        help="Path to fellows.db. Defaults to FELLOWS_DB_PATH or <repo>/app/fellows.db.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Log tool calls and resolved args to stderr.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    global _DB_PATH
    _DB_PATH = _resolve_db_path(args.db)
    if not _DB_PATH.is_file():
        print(f"fellows.db not found at {_DB_PATH}", file=sys.stderr)
        print("Run: just db-rebuild", file=sys.stderr)
        return 1
    # Sanity-check we can open it read-only before handing control to the
    # stdio loop — fail fast with a useful stderr message rather than a
    # cryptic JSON-RPC error on the first tool call.
    try:
        with get_db_readonly(_DB_PATH) as conn:
            conn.execute("SELECT 1 FROM fellows LIMIT 1").fetchone()
    except sqlite3.Error as e:
        print(f"Cannot open {_DB_PATH} read-only: {e}", file=sys.stderr)
        return 1

    log.info("shared-data-ops MCP server starting; db=%s", _DB_PATH)
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
