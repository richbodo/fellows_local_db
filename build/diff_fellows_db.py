#!/usr/bin/env python3
"""Diff two fellows.db files column-by-column.

Used to verify that ``build/restore_from_knack_scrapefile.py`` reproduces
``app/fellows.db.backup.2026-04-08`` exactly. Reports per-column mismatch
counts and shows a handful of example rows.

Usage:
    python build/diff_fellows_db.py new.db ref.db
"""
import argparse
import json
import sqlite3
import sys

COLS = [
    "record_id", "slug", "name", "bio_tagline", "fellow_type", "cohort",
    "contact_email", "key_links", "key_links_urls", "image_url",
    "currently_based_in", "search_tags", "fellow_status", "gender_pronouns",
    "ethnicity", "primary_citizenship", "global_regions_currently_based_in",
    "extra_json",
]


def dump(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = {}
    for r in conn.execute(f"SELECT {','.join(COLS)} FROM fellows"):
        rows[r["record_id"]] = dict(r)
    conn.close()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("new_db")
    ap.add_argument("ref_db")
    ap.add_argument("--show", type=int, default=3,
                    help="Show N example mismatches per column (default 3)")
    args = ap.parse_args()

    new = dump(args.new_db)
    ref = dump(args.ref_db)

    only_in_new = sorted(set(new) - set(ref))
    only_in_ref = sorted(set(ref) - set(new))
    common = sorted(set(new) & set(ref))

    print(f"new: {len(new)} rows, ref: {len(ref)} rows, common: {len(common)}")
    if only_in_new:
        print(f"  only in new: {len(only_in_new)}  first: {only_in_new[:3]}")
    if only_in_ref:
        print(f"  only in ref: {len(only_in_ref)}  first: {only_in_ref[:3]}")

    mismatches = {c: [] for c in COLS if c != "record_id"}
    for rid in common:
        for col in COLS:
            if col == "record_id":
                continue
            nv = new[rid][col]
            rv = ref[rid][col]
            # Normalise JSON columns before diffing
            if col == "extra_json":
                try:
                    nv_j = json.loads(nv) if nv else {}
                    rv_j = json.loads(rv) if rv else {}
                    if nv_j == rv_j:
                        continue
                    diff_keys = []
                    for k in set(nv_j) | set(rv_j):
                        if nv_j.get(k) != rv_j.get(k):
                            diff_keys.append(k)
                    mismatches[col].append((rid, f"extra keys differ: {sorted(diff_keys)[:4]}"))
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            if nv != rv:
                mismatches[col].append((rid, f"new={nv!r}  ref={rv!r}"))

    print("\nPer-column mismatch counts:")
    total_mismatches = 0
    for col in COLS:
        if col == "record_id":
            continue
        n = len(mismatches[col])
        total_mismatches += n
        marker = "✓" if n == 0 else "✗"
        print(f"  {marker} {col}: {n}")

    if total_mismatches == 0:
        print("\n✓ bytewise match on all columns")
        return 0

    print(f"\n✗ {total_mismatches} total mismatches. Examples:")
    for col, items in mismatches.items():
        if not items:
            continue
        print(f"\n--- {col} ({len(items)}) ---")
        for rid, msg in items[: args.show]:
            ref_row = ref.get(rid, {})
            print(f"  {rid} [{ref_row.get('name')}]")
            print(f"    {msg[:200]}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
