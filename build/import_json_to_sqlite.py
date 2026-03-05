#!/usr/bin/env python3
"""
Import EHF fellow profiles from JSON into SQLite with FTS5.
Reads: final_fellows_set/ehf_fellow_profiles_deduped.json
Writes: app/fellows.db (fellows table + fellows_fts FTS5 virtual table)

Run from repo root: python build/import_json_to_sqlite.py
"""

import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

# Paths relative to repo root (where script is run from)
REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "final_fellows_set" / "ehf_fellow_profiles_deduped.json"
DB_PATH = REPO_ROOT / "app" / "fellows.db"

# Columns we store explicitly for display/search; rest go into extra_json
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
]
EXTRA_JSON_KEYS = None  # All keys not in FELLOW_COLUMNS go into extra_json


def slugify(text: str) -> str:
    """Derive URL-safe slug: lowercase, spaces and non-alphanumeric -> underscores."""
    if not text or not str(text).strip():
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")
    return slug or ""


def get_slug(record: dict) -> str:
    """Get slug from name or table_name; fallback to record_id."""
    name = (record.get("name") or "").strip()
    table_name = (record.get("table_name") or "").strip()
    display = name or table_name
    if display:
        return slugify(display)
    return (record.get("record_id") or "").strip() or "unknown"


def get_name(record: dict) -> str:
    """Display name: name or table_name."""
    name = (record.get("name") or "").strip()
    if name:
        return name
    return (record.get("table_name") or "").strip() or ""


def serialize_value(v):
    """JSON-serialize lists/dicts for storage."""
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v) if v else None
    return str(v).strip() or None


def build_row(record: dict) -> tuple:
    """Build a single row for fellows table (order matches FELLOW_COLUMNS + extra_json)."""
    slug = record.get("_slug") or get_slug(record)
    name = get_name(record)
    row = {
        "record_id": (record.get("record_id") or "").strip() or None,
        "slug": slug or None,
        "name": name or None,
        "bio_tagline": serialize_value(record.get("bio_tagline")),
        "fellow_type": serialize_value(record.get("fellow_type")),
        "cohort": serialize_value(record.get("cohort")),
        "contact_email": serialize_value(record.get("contact_email")),
        "key_links": serialize_value(record.get("key_links")),
        "key_links_urls": serialize_value(record.get("key_links_urls")),
        "image_url": serialize_value(record.get("image_url")),
        "currently_based_in": serialize_value(record.get("currently_based_in")),
        "search_tags": serialize_value(record.get("search_tags")),
        "fellow_status": serialize_value(record.get("fellow_status")),
        "gender_pronouns": serialize_value(record.get("gender_pronouns")),
        "ethnicity": serialize_value(record.get("ethnicity")),
        "primary_citizenship": serialize_value(record.get("primary_citizenship")),
        "global_regions_currently_based_in": serialize_value(record.get("global_regions_currently_based_in")),
    }
    extra = {k: v for k, v in record.items() if k not in FELLOW_COLUMNS}
    row["extra_json"] = json.dumps(extra) if extra else None
    return tuple(row.get(c) for c in FELLOW_COLUMNS) + (row["extra_json"],)


def main():
    REPO_ROOT.mkdir(exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Back up existing DB before overwriting
    if DB_PATH.exists():
        backup_name = f"fellows.db.backup.{date.today().isoformat()}"
        shutil.copy2(DB_PATH, DB_PATH.parent / backup_name)
        print(f"Backed up existing DB to app/{backup_name}")

    if not JSON_PATH.exists():
        raise SystemExit(f"JSON not found: {JSON_PATH}")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        raise SystemExit("No records in JSON")

    # Ensure unique slugs: first occurrence keeps base slug, later get _1, _2, ...
    slug_counts = {}
    for r in records:
        s = get_slug(r)
        slug_counts[s] = slug_counts.get(s, 0) + 1
    duplicates = {s for s, c in slug_counts.items() if c > 1}
    next_suffix = {s: 0 for s in duplicates}
    for r in records:
        s = get_slug(r)
        if s in duplicates:
            if next_suffix[s] == 0:
                r["_slug"] = s
                next_suffix[s] = 1
            else:
                r["_slug"] = f"{s}_{next_suffix[s]}"
                next_suffix[s] += 1
        else:
            r["_slug"] = s

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Create fellows table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fellows (
            record_id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            name TEXT,
            bio_tagline TEXT,
            fellow_type TEXT,
            cohort TEXT,
            contact_email TEXT,
            key_links TEXT,
            key_links_urls TEXT,
            image_url TEXT,
            currently_based_in TEXT,
            search_tags TEXT,
            fellow_status TEXT,
            gender_pronouns TEXT,
            ethnicity TEXT,
            primary_citizenship TEXT,
            global_regions_currently_based_in TEXT,
            extra_json TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fellows_slug ON fellows(slug)")

    conn.execute("DELETE FROM fellows")
    cols = FELLOW_COLUMNS + ["extra_json"]
    placeholders = ",".join("?" * len(cols))
    for r in records:
        row = build_row(r)
        conn.execute(
            f"INSERT OR REPLACE INTO fellows ({','.join(cols)}) VALUES ({placeholders})",
            row,
        )

    # FTS5 virtual table (external content) over fellows
    conn.execute("DROP TABLE IF EXISTS fellows_fts")
    conn.execute("""
        CREATE VIRTUAL TABLE fellows_fts USING fts5(
            name,
            bio_tagline,
            cohort,
            fellow_type,
            search_tags,
            key_links,
            content='fellows',
            content_rowid='rowid'
        )
    """)
    conn.execute("INSERT INTO fellows_fts(fellows_fts) VALUES('rebuild')")

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]
    conn.close()

    print(f"Imported {count} fellows into {DB_PATH}")
    print("Verify: sqlite3 app/fellows.db \"SELECT name, slug FROM fellows ORDER BY name LIMIT 3;\"")
    print("FTS5:   sqlite3 app/fellows.db \"SELECT rowid, name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
