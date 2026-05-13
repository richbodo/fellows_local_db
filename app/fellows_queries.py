"""Pure-logic query helpers over ``fellows.db``.

Shared between the dev HTTP server (``app/server.py``) and the MCP data-ops
server in ``mcp/`` so both surface identical record shapes. No HTTP, no
framework, no global state — just SQL helpers and the ``row_to_fellow``
shape that merges ``extra_json`` overflow keys into the record.
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "fellows.db"

FELLOW_COLUMNS = [
    "record_id", "slug", "name", "bio_tagline", "fellow_type", "cohort",
    "contact_email", "key_links", "key_links_urls", "image_url",
    "currently_based_in", "search_tags", "fellow_status", "gender_pronouns",
    "ethnicity", "primary_citizenship", "global_regions_currently_based_in",
    "has_image",
]


def row_to_fellow(row) -> dict:
    """Convert DB row (dict-like) to API fellow object; parse JSON columns and merge extra_json."""
    if hasattr(row, "keys"):
        row = {k: row[k] for k in row.keys()}
    out = {}
    for key in FELLOW_COLUMNS:
        val = row.get(key)
        if key == "key_links_urls" and val is not None:
            try:
                out[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                out[key] = val
        else:
            out[key] = val
    if row.get("extra_json"):
        try:
            extra = json.loads(row["extra_json"])
            if isinstance(extra, dict):
                out.update(extra)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def get_db(db_path: Path | str | None = None):
    """Return a read-write DB connection, or None if the file is absent."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_readonly(db_path: Path | str | None = None):
    """Return a read-only DB connection (SQLite URI ``mode=ro``).

    Used by the MCP server so even a buggy tool can't mutate the directory
    snapshot. Raises ``sqlite3.OperationalError`` if the file is missing,
    rather than returning None — callers should fail fast.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_fellows(conn) -> list:
    cur = conn.execute("SELECT * FROM fellows ORDER BY name ASC")
    return [row_to_fellow(row) for row in cur.fetchall()]


def get_fellows_list(conn) -> list:
    """Minimal list for instant directory: record_id, slug, name, has_contact_email."""
    cur = conn.execute(
        "SELECT record_id, slug, name,"
        " CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END"
        " AS has_contact_email"
        " FROM fellows ORDER BY name ASC"
    )
    rows = cur.fetchall()
    return [
        {"record_id": r[0], "slug": r[1], "name": r[2], "has_contact_email": bool(r[3])}
        for r in rows
    ]


def get_fellow_by_slug_or_id(conn, slug_or_id: str) -> dict | None:
    cur = conn.execute(
        "SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1",
        (slug_or_id, slug_or_id),
    )
    row = cur.fetchone()
    return row_to_fellow(row) if row else None


def search_fellows(conn, q: str) -> list:
    if not (q or q.strip()):
        return []
    q = q.strip()
    if len(q) > 200:
        q = q[:200]
    cur = conn.execute(
        """
        SELECT f.* FROM fellows f
        WHERE f.rowid IN (
            SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?
        )
        ORDER BY f.name ASC
        """,
        (q,),
    )
    return [row_to_fellow(row) for row in cur.fetchall()]


def get_stats(conn) -> dict:
    """Aggregate statistics for the stats page."""
    total = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]

    def group_counts(sql):
        return [{"label": r[0], "count": r[1]} for r in conn.execute(sql).fetchall()]

    region_counter: Counter = Counter()
    for row in conn.execute(
        "SELECT global_regions_currently_based_in FROM fellows"
        " WHERE global_regions_currently_based_in IS NOT NULL"
        " AND global_regions_currently_based_in != ''"
    ).fetchall():
        for region in row[0].split(","):
            region = region.strip()
            if region:
                region_counter[region] += 1
    by_region = [{"label": r, "count": c} for r, c in region_counter.most_common()]

    field_counts = []
    col_labels = {
        "name": "Name", "bio_tagline": "Bio / Tagline", "fellow_type": "Fellow Type",
        "cohort": "Cohort", "contact_email": "Contact Email", "key_links": "Key Links",
        "image_url": "Image URL", "currently_based_in": "Currently Based In",
        "search_tags": "Search Tags", "fellow_status": "Fellow Status",
        "gender_pronouns": "Gender / Pronouns", "ethnicity": "Ethnicity",
        "primary_citizenship": "Primary Citizenship",
        "global_regions_currently_based_in": "Global Regions Based In",
    }
    for col, label in col_labels.items():
        count = conn.execute(
            f"SELECT COUNT(*) FROM fellows WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchone()[0]
        field_counts.append({"label": label, "count": count})
    extra_labels = {
        "all_citizenships": "All Citizenships",
        "ventures": "Ventures", "industries": "Industries",
        "career_highlights": "Career Highlights",
        "key_networks": "Key Networks",
        "how_im_looking_to_support_the_nz_ecosystem": "How Supporting NZ Ecosystem",
        "what_is_your_main_mode_of_working": "Main Mode of Working",
        "do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories": "Investor Categories",
        "mobile_number": "Mobile Number",
        "five_things_to_know": "Five Things to Know",
        "skills_to_give": "Skills to Give",
        "skills_to_receive": "Skills to Receive",
    }
    for key, label in extra_labels.items():
        count = conn.execute(
            "SELECT COUNT(*) FROM fellows WHERE extra_json IS NOT NULL"
            " AND json_extract(extra_json, ?) IS NOT NULL"
            " AND json_extract(extra_json, ?) != ''",
            (f"$.{key}", f"$.{key}"),
        ).fetchone()[0]
        field_counts.append({"label": label, "count": count})
    field_counts.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total": total,
        "by_fellow_type": group_counts(
            "SELECT fellow_type, COUNT(*) FROM fellows"
            " WHERE fellow_type IS NOT NULL"
            " GROUP BY fellow_type ORDER BY COUNT(*) DESC"
        ),
        "by_cohort": group_counts(
            "SELECT cohort, COUNT(*) FROM fellows"
            " WHERE cohort IS NOT NULL"
            " GROUP BY cohort ORDER BY COUNT(*) DESC"
        ),
        "by_region": by_region,
        "field_completeness": field_counts,
    }
