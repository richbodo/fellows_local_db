#!/usr/bin/env python3
"""Build app/fellows.db from a Knack REST-API detail-dump JSON.

Takes a Knack scrapefile (detail-dump shape: dict keyed by record_id, each
value a dict of Knack field_XXX fields) and produces a clean fellows.db.
Replaces the stopgap ``restore_from_knack_apr8.py`` which could only copy
a pre-built backup DB.

Usage:
    python build/restore_from_knack_scrapefile.py \\
        final_fellows_set/knack_api_detail_dump.json

    # Or with a different source:
    python build/restore_from_knack_scrapefile.py /path/to/other_scrape.json

Field provenance: see the KNACK_FIELD_MAP below. Every schema column traces
back to a specific Knack ``field_XXX`` or to a pure-function derivation of
one. Unmapped fields don't end up in the DB; intentionally mapped-to-
``extra_json`` fields do.

Strict reproduction: the output is expected to match
``app/fellows.db.backup.2026-04-08`` column-by-column for the 515 fellows
in the 2026-04-08 scrape. The accompanying ``build/diff_fellows_db.py``
(see docs/data_provenance.md) compares the two DBs and reports mismatches.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "app" / "fellows.db"
IMAGES_DIR_SOURCE = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"
IMAGES_DIR_APP = REPO_ROOT / "app" / "fellow_profile_images_by_name"

# ─────────────────────────────────────────────────────────────────────────────
# Field provenance. Each tuple: (db_column_or_extra_json_key, knack_field_id,
# kind). Kind determines how the raw Knack value gets normalised.
#
# kind values:
#   'plain'         : copy as-is (already plain text)
#   'strip_span'    : strip <span …>VALUE</span> wrappers, keep inner text
#   'strip_br'      : replace <br /> with a space, then collapse whitespace
#   'strip_both'    : strip_span + strip_br
#   'multi_span'    : Knack connection list — join span-inner-texts with ', '
#   'multi_br'      : Knack multi-select — values separated by <br />, joined ', '
#   'email'         : pull from field_XXX_raw.email (clean) rather than HTML
#   'img_url'       : pull src= from <img> HTML
#   'linklabels'    : Knack connection list of <a> tags — join inner texts
#   'linkurls'      : Knack connection list of <a> tags — JSON array of hrefs
#   'linkurls_mailto' : single mailto: URL derived from raw email
# ─────────────────────────────────────────────────────────────────────────────

# DB columns mapped directly to Knack fields.
KNACK_FIELD_MAP_COLS = [
    # (column, field_id, kind)
    # name: prefer field_10_raw.full which preserves internal whitespace
    # (e.g. "Daniel  Price" with a double space that field_10 collapses).
    ("name", "field_10", "name_full"),
    ("bio_tagline", "field_319", "plain_br_newline"),
    # fellow_type: field_720 in detail dump when present; falls back to
    # raw_dump's field_649 for fellows without a detail-level type.
    ("fellow_type", "field_720|raw:field_649", "plain"),
    ("cohort", "field_311", "strip_span"),
    ("contact_email", "field_776", "email"),
    ("image_url", "field_299", "img_url"),
    # currently_based_in: join each address's `full` from the _raw list,
    # preserving the original Apr 8 multi-address joining with '\n'.
    ("currently_based_in", "field_617", "address_list_full"),
    ("search_tags", "field_402", "plain"),
    ("fellow_status", "field_648", "plain"),
    ("gender_pronouns", "field_740", "plain"),
    ("ethnicity", "field_722", "multi_span"),
    # primary_citizenship: sourced from field_646 (a dedicated single-value
    # field), NOT field_393 which is the full citizenships list.
    ("primary_citizenship", "field_646", "strip_span"),
    ("global_regions_currently_based_in", "field_645", "multi_span"),
]

# extra_json keys and their field_XXX sources. Field mappings discovered by
# matching Apr 8 DB values against detail-dump fields across all 515 records
# — see docs/data_provenance.md for the rationale. The five "non-obvious"
# mappings (sdgs, key_networks, industries_other, ventures,
# other_fellows_in_team) were misnamed in my first pass; these are correct.
KNACK_FIELD_MAP_EXTRA = [
    ("mobile_number", "field_738", "verbatim"),
    ("all_citizenships", "field_393", "multi_span"),
    ("primary_global_region_of_citizenship", "field_647", "strip_span"),
    ("global_networks", "field_403", "multi_span"),
    ("ventures", "field_858", "anchor_list"),
    ("industries", "field_349", "multi_span"),
    ("industries_other", "field_652", "plain_raw"),
    ("what_is_your_main_mode_of_working", "field_755", "multi_identifier"),
    ("do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories", "field_758", "multi_identifier"),
    ("what_are_the_main_types_of_organisations_you_serve", "field_810", "multi_identifier"),
    ("career_highlights", "field_812", "plain_raw"),
    ("how_im_looking_to_support_the_nz_ecosystem", "field_400", "plain_raw"),
    ("key_networks", "field_397", "plain_raw"),
    ("impact_goals_nz", "field_398", "plain_raw"),
    ("how_to_support_my_work", "field_399", "plain_raw"),
    ("five_things_to_know", "field_300", "plain_raw"),
    ("anything_else_to_share", "field_775", "plain_raw"),
    ("other_fellows_in_team", "field_654", "multi_span"),
    ("how_fellows_can_connect", "field_766", "multi_identifier"),
    ("skills_to_give", "field_770", "multi_identifier"),
    ("skills_to_receive", "field_771", "multi_identifier"),
    ("sdgs", "field_396", "multi_identifier"),
    ("this_profile_last_updated", "field_449", "plain"),
]

# Key links get a bespoke extraction (labels + URLs from HTML <a> list).
KEY_LINKS_FIELD = "field_710"

# ─────────────────────────────────────────────────────────────────────────────

_SPAN_RE = re.compile(r"<span\b[^>]*>(.*?)</span>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'<img\b[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
_ANCHOR_TEXT_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)


def _inner_text(s: str) -> str:
    """Strip all tags from an HTML snippet, collapse whitespace."""
    s = _TAG_RE.sub("", s)
    s = s.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def normalise(kind: str, value: Any, raw_value: Any = None) -> Any:
    """Convert a Knack field value per its 'kind'. Returns None/empty→None."""
    if value is None or value == "" or value == []:
        if kind == "email" and isinstance(raw_value, dict) and raw_value.get("email"):
            return str(raw_value["email"]).strip() or None
        return None

    if kind == "plain":
        return str(value).strip() or None

    if kind == "verbatim":
        # Pass through as-is except for outright None/empty. Preserves any
        # trailing whitespace Apr 8 captured verbatim from Knack (rare).
        return str(value) if str(value) != "" else None

    if kind == "plain_preserve":
        # Plain text, preserve internal whitespace exactly (no collapse).
        # Apr 8 DB has rows like "Daniel  Price" with a double space we keep.
        s = str(value)
        return s.strip("\n\r\t ") or None

    if kind == "plain_br_newline":
        # Plain text with <br /> → \n. Used for bio_tagline and similar
        # multi-line plain strings where Apr 8 preserved line breaks as \n.
        s = _BR_RE.sub("\n", str(value))
        return s.strip("\n\r\t ") or None

    if kind == "strip_span":
        # Single connection-value. Strip <span> wrapper, return inner text.
        m = _SPAN_RE.search(str(value))
        return (m.group(1).strip() if m else _inner_text(str(value))) or None

    if kind == "last_span":
        # Multi-value connection list; take the LAST span's inner text.
        # Apr 8 ETL's primary_citizenship convention.
        parts = [m.group(1).strip() for m in _SPAN_RE.finditer(str(value))]
        parts = [p for p in parts if p]
        return parts[-1] if parts else None

    if kind == "strip_br":
        s = _BR_RE.sub(" ", str(value))
        return _inner_text(s) or None

    if kind == "strip_both":
        # Single span that may contain <br />. Strip <br /> first, then the span.
        s = _BR_RE.sub(" ", str(value))
        m = _SPAN_RE.search(s)
        return (m.group(1).strip() if m else _inner_text(s)) or None

    if kind == "strip_both_preserve":
        # Same as strip_both but don't collapse whitespace — Apr 8 keeps
        # sequential spaces like "Grey Lynn  New Zealand".
        s = _BR_RE.sub(" ", str(value))
        m = _SPAN_RE.search(s)
        inner = m.group(1) if m else re.sub(r"<[^>]+>", "", s)
        return inner.strip() or None

    if kind == "multi_span":
        # Comma-joined span-wrapped values. Split on the ', ' between spans.
        parts = [m.group(1).strip() for m in _SPAN_RE.finditer(str(value))]
        parts = [p for p in parts if p]
        return ", ".join(parts) or None

    if kind == "multi_br":
        # <span>A</span><br /><span>B</span> — break on <br />, then span-strip each.
        chunks = _BR_RE.split(str(value))
        parts = []
        for c in chunks:
            m = _SPAN_RE.search(c)
            inner = (m.group(1).strip() if m else _inner_text(c))
            if inner:
                parts.append(inner)
        return ", ".join(parts) or None

    if kind == "email":
        # Prefer the raw form's clean email; fall back to parsing the HTML.
        if isinstance(raw_value, dict) and raw_value.get("email"):
            return str(raw_value["email"]).strip() or None
        m = re.search(r"mailto:([^\"'>]+)", str(value))
        return m.group(1).strip() if m else None

    if kind == "img_url":
        m = _IMG_SRC_RE.search(str(value))
        return m.group(1) if m else None

    if kind == "name_full":
        # Prefer the raw name dict's `full` (preserves double-spaces).
        if isinstance(raw_value, dict) and raw_value.get("full"):
            return str(raw_value["full"]).strip("\n\r\t ") or None
        return str(value).strip() or None

    if kind == "plain_raw":
        # Free-text field: prefer _raw string (has real \n) over the rendered
        # HTML version (has literal <br /> tags). Apr 8 wrote \n form; using
        # _raw matches that exactly.
        src = raw_value if isinstance(raw_value, str) else str(value)
        return src.strip("\n\r\t ") or None

    if kind == "anchor_list":
        # _raw is a list whose items are either plain strings ('Healing Hive')
        # OR <a href>LABEL</a> HTML strings ('<a …>CommunityShare</a>').
        # Both shapes appear in the Knack dump across fellows. Extract the
        # label from either form, join with ', '.
        if isinstance(raw_value, list):
            labels = []
            for item in raw_value:
                s = str(item)
                m = _ANCHOR_TEXT_RE.search(s)
                labels.append(_inner_text(m.group(1)) if m else s.strip())
            labels = [l for l in labels if l]
            return ", ".join(labels) or None
        # Fallback: pull from rendered HTML.
        labels = []
        for m in _ANCHOR_TEXT_RE.finditer(str(value)):
            labels.append(_inner_text(m.group(1)))
        labels = [l for l in labels if l]
        return ", ".join(labels) or None

    if kind == "multi_identifier":
        # Multi-value connection: use _raw list's `identifier` strings,
        # joined with ', '. Preserves trailing spaces in identifiers
        # (some Knack admin entries had them; Apr 8 kept them).
        if isinstance(raw_value, list):
            parts = [str(e.get("identifier", "")) for e in raw_value if isinstance(e, dict)]
            parts = [p for p in parts if p]
            return ", ".join(parts) or None
        # Fallback: multi_br behaviour.
        chunks = _BR_RE.split(str(value))
        parts = []
        for c in chunks:
            m = _SPAN_RE.search(c)
            inner = (m.group(1) if m else _inner_text(c))
            if inner:
                parts.append(inner)
        return ", ".join(parts) or None

    if kind == "address_list_full":
        # Use field_617_raw's list, joining each entry's `full` with '\n'.
        # Strip each entry (some Knack records have trailing spaces in
        # `full`) but preserve internal whitespace (double spaces matter).
        if isinstance(raw_value, list):
            parts = [str(e.get("full", "")).strip() for e in raw_value if isinstance(e, dict)]
            parts = [p for p in parts if p]
            return "\n".join(parts) or None
        # Single-value fallback — mirror the old strip_both_preserve.
        s = _BR_RE.sub(" ", str(value))
        m = _SPAN_RE.search(s)
        inner = m.group(1) if m else re.sub(r"<[^>]+>", "", s)
        return inner.strip() or None

    raise ValueError(f"unknown kind: {kind}")


def _resolve_field(raw_detail: dict, raw_supp: dict, field_spec: str) -> tuple[Any, Any]:
    """Resolve a field spec that may fall back to a secondary source.

    Spec syntax: "field_A|raw:field_B" — prefer detail[field_A], else
    raw_supp[field_B]. Returns (value, value_raw).
    """
    parts = field_spec.split("|")
    for part in parts:
        if part.startswith("raw:"):
            fid = part[len("raw:"):]
            src = raw_supp
        else:
            fid = part
            src = raw_detail
        if src is None:
            continue
        v = src.get(fid)
        if v not in (None, "", []):
            return v, src.get(f"{fid}_raw")
    return None, None


def extract_key_links(raw_record: dict) -> tuple[str | None, str | None]:
    """Pull 'LinkedIn, Wiki' and '[url1, url2]' from field_710's HTML soup."""
    html = raw_record.get(KEY_LINKS_FIELD) or ""
    if not html:
        return None, None
    labels = []
    urls = []
    for m in _ANCHOR_TEXT_RE.finditer(html):
        inner_html = m.group(0)
        href_m = _HREF_RE.search(inner_html)
        label = _inner_text(m.group(1))
        if label:
            labels.append(label)
        if href_m:
            urls.append(href_m.group(1))
    labels_str = ", ".join(labels) if labels else None
    urls_str = json.dumps(urls) if urls else None
    return labels_str, urls_str


def slugify(text: str) -> str:
    if not text or not str(text).strip():
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_") or ""


def build_image_index() -> dict[str, Path]:
    d = IMAGES_DIR_SOURCE if IMAGES_DIR_SOURCE.is_dir() else (IMAGES_DIR_APP if IMAGES_DIR_APP.is_dir() else None)
    if not d:
        return {}
    idx: dict[str, Path] = {}
    for p in d.iterdir():
        if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        stem_alpha = re.sub(r"[^a-z0-9]", "", p.stem.lower())
        if stem_alpha and stem_alpha not in idx:
            idx[stem_alpha] = p
    return idx


def slug_has_image(slug: str, image_index: dict) -> int:
    if not slug or not image_index:
        return 0
    base_alpha = re.sub(r"[^a-z0-9]", "", slug.split("/")[-1].split(".")[0].lower())
    return 1 if base_alpha in image_index else 0


def _format_last_updated(raw: dict) -> str:
    """Render field_449 as Apr 8 did: '{date_formatted} {time_formatted}'.

    date_formatted is 'DD/MM/YYYY'; time_formatted is zero-padded
    'HH:MMam' / 'HH:MMpm'. Falls back to the plain field_449 string if
    the raw dict is absent.
    """
    rv = raw.get("field_449_raw")
    if isinstance(rv, dict):
        date_s = rv.get("date_formatted") or ""
        time_s = rv.get("time_formatted") or ""
        if date_s and time_s:
            return f"{date_s} {time_s}"
    # Fallback
    return str(raw.get("field_449") or "").strip()


def build_row(
    rid: str,
    raw_detail: dict,
    raw_supp: dict,
    image_index: dict,
    slug_counts: dict[str, int],
    slug_used: dict[str, int],
) -> tuple[dict, dict]:
    """Produce (cols_row, extra_dict) for one fellow.

    raw_detail is the per-record dict from knack_api_detail_dump.json.
    raw_supp is the corresponding record from knack_api_raw_dump.json
    (search view), which carries fields the detail dump lacks (e.g.
    field_649 for fellow_type).
    """
    name_v, name_rv = _resolve_field(raw_detail, raw_supp, "field_10")
    name = normalise("name_full", name_v, name_rv)

    base_slug = slugify(name) or (rid or "unknown")
    if slug_counts.get(base_slug, 0) > 1:
        n = slug_used.get(base_slug, 0)
        slug = base_slug if n == 0 else f"{base_slug}_{n}"
        slug_used[base_slug] = n + 1
    else:
        slug = base_slug

    cols: dict[str, Any] = {"record_id": rid, "slug": slug, "name": name}
    # Skip name entry (already handled).
    for col, field_spec, kind in KNACK_FIELD_MAP_COLS[1:]:
        v, vr = _resolve_field(raw_detail, raw_supp, field_spec)
        cols[col] = normalise(kind, v, vr)

    key_links, key_links_urls = extract_key_links(raw_detail)
    cols["key_links"] = key_links
    cols["key_links_urls"] = key_links_urls

    extra: dict[str, Any] = {}
    for k, field_spec, kind in KNACK_FIELD_MAP_EXTRA:
        if k == "this_profile_last_updated":
            extra[k] = _format_last_updated(raw_detail)
            continue
        v, vr = _resolve_field(raw_detail, raw_supp, field_spec)
        extra[k] = normalise(kind, v, vr) or ""

    # contact_email_urls: actual list, NOT a JSON-encoded string.
    em_v, em_rv = _resolve_field(raw_detail, raw_supp, "field_776")
    em = normalise("email", em_v, em_rv)
    extra["contact_email_urls"] = [f"mailto:{em}"] if em else ""

    extra["_slug"] = slug

    cols["has_image"] = slug_has_image(slug, image_index)
    return cols, extra


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "scrapefile",
        nargs="?",
        default=str(REPO_ROOT / "final_fellows_set" / "knack_api_detail_dump.json"),
        help="Path to Knack detail-dump JSON (defaults to final_fellows_set/knack_api_detail_dump.json).",
    )
    ap.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Output DB path (default: {DB_PATH}).",
    )
    args = ap.parse_args(argv)

    src = Path(args.scrapefile)
    if not src.is_file():
        print(f"Scrapefile not found: {src}", file=sys.stderr)
        return 1

    with open(src, "r", encoding="utf-8") as f:
        detail = json.load(f)
    if not isinstance(detail, dict):
        print(f"Expected dict-of-records at top level; got {type(detail).__name__}", file=sys.stderr)
        return 1

    # Supplementary dump (raw_dump) — used for fields the detail dump lacks
    # (notably field_649 → fellow_type on some fellows). Loaded automatically
    # from the sibling knack_api_raw_dump.json if present; absent is fine.
    raw_dump_by_id: dict[str, dict] = {}
    supp_path = src.parent / "knack_api_raw_dump.json"
    if supp_path.is_file():
        with open(supp_path, "r", encoding="utf-8") as f:
            raw_dump = json.load(f)
        # Structure: {'public': [...], 'alumni': [...], 'search': [...]}.
        # 'search' has all 515; iterate all views and take the first record
        # seen per id (no conflicts observed across views).
        for view in ("search", "alumni", "public"):
            for r in raw_dump.get(view, []):
                rid = r.get("id")
                if rid and rid not in raw_dump_by_id:
                    raw_dump_by_id[rid] = r
        print(f"Loaded supplementary raw_dump: {len(raw_dump_by_id)} records")
    else:
        print(f"Note: {supp_path.name} not found; some fields may be missing")

    db_out = Path(args.db)
    if db_out.is_file():
        backup_name = f"fellows.db.before-scrapefile-import.{date.today().isoformat()}"
        shutil.copy2(db_out, db_out.parent / backup_name)
        print(f"Backed up existing DB to {db_out.parent / backup_name}")

    if db_out.exists():
        db_out.unlink()

    conn = sqlite3.connect(db_out)
    conn.execute("""
        CREATE TABLE fellows (
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
            has_image INTEGER NOT NULL DEFAULT 0,
            extra_json TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX idx_fellows_slug ON fellows(slug)")

    image_index = build_image_index()

    # First pass: compute slugs to detect duplicates.
    slug_counts: dict[str, int] = {}
    for rid, raw in detail.items():
        name = str(raw.get("field_10") or "").strip()
        s = slugify(name) or (rid or "unknown")
        slug_counts[s] = slug_counts.get(s, 0) + 1

    slug_used: dict[str, int] = {}
    cols_order = [
        "record_id", "slug", "name", "bio_tagline", "fellow_type", "cohort",
        "contact_email", "key_links", "key_links_urls", "image_url",
        "currently_based_in", "search_tags", "fellow_status", "gender_pronouns",
        "ethnicity", "primary_citizenship", "global_regions_currently_based_in",
        "has_image", "extra_json",
    ]
    placeholders = ",".join("?" * len(cols_order))
    for rid, raw in detail.items():
        raw_supp = raw_dump_by_id.get(rid, {})
        cols, extra = build_row(rid, raw, raw_supp, image_index, slug_counts, slug_used)
        cols["extra_json"] = json.dumps(extra) if extra else None
        row = tuple(cols.get(c) for c in cols_order)
        conn.execute(
            f"INSERT INTO fellows ({','.join(cols_order)}) VALUES ({placeholders})",
            row,
        )

    conn.execute("""
        CREATE VIRTUAL TABLE fellows_fts USING fts5(
            name, bio_tagline, cohort, fellow_type, search_tags, key_links,
            content='fellows', content_rowid='rowid'
        )
    """)
    conn.execute("INSERT INTO fellows_fts(fellows_fts) VALUES('rebuild')")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]
    with_image = conn.execute("SELECT COUNT(*) FROM fellows WHERE has_image = 1").fetchone()[0]
    with_email = conn.execute(
        "SELECT COUNT(*) FROM fellows WHERE contact_email IS NOT NULL AND trim(contact_email) != ''"
    ).fetchone()[0]
    conn.close()

    print(f"Built {db_out}: {count} fellows, {with_image} with image, {with_email} with email")
    print(
        "Verify vs backup:\n"
        f"  python build/diff_fellows_db.py {db_out} app/fellows.db.backup.2026-04-08"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
