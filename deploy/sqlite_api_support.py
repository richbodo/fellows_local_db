"""Read-only SQLite helpers for deploy/server.py (same semantics as app/server.py)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

FELLOW_COLUMNS = [
    "record_id",
    "slug",
    "name",
    "bio_tagline",
    "fellow_type",
    "cohort",
    "contact_email",
    "key_links",
    "key_links_urls",
    "image_url",
    "currently_based_in",
    "search_tags",
    "fellow_status",
    "gender_pronouns",
    "ethnicity",
    "primary_citizenship",
    "global_regions_currently_based_in",
    "has_image",
]


def row_to_fellow(row) -> dict:
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


def connect(db_path: Path):
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_all_fellows(conn) -> list:
    cur = conn.execute("SELECT * FROM fellows ORDER BY name ASC")
    return [row_to_fellow(row) for row in cur.fetchall()]


def get_fellows_list(conn) -> list:
    cur = conn.execute("SELECT record_id, slug, name FROM fellows ORDER BY name ASC")
    rows = cur.fetchall()
    return [{"record_id": r[0], "slug": r[1], "name": r[2]} for r in rows]


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
    total = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]

    def group_counts(sql: str):
        return [{"label": r[0], "count": r[1]} for r in conn.execute(sql).fetchall()]

    region_counter: Counter[str] = Counter()
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

    col_labels = {
        "name": "Name",
        "bio_tagline": "Bio / Tagline",
        "fellow_type": "Fellow Type",
        "cohort": "Cohort",
        "contact_email": "Contact Email",
        "key_links": "Key Links",
        "image_url": "Image URL",
        "currently_based_in": "Currently Based In",
        "search_tags": "Search Tags",
        "fellow_status": "Fellow Status",
        "gender_pronouns": "Gender / Pronouns",
        "ethnicity": "Ethnicity",
        "primary_citizenship": "Primary Citizenship",
        "global_regions_currently_based_in": "Global Regions Based In",
    }
    field_counts = []
    for col, label in col_labels.items():
        count = conn.execute(
            f"SELECT COUNT(*) FROM fellows WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchone()[0]
        field_counts.append({"label": label, "count": count})
    extra_labels = {
        "all_citizenships": "All Citizenships",
        "ventures": "Ventures",
        "industries": "Industries",
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
