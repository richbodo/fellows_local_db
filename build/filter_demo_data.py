#!/usr/bin/env python3
"""
Filter fellow profiles to only those with a name AND a local image file.
Reads:  final_fellows_set/ehf_fellow_profiles_deduped.json
Writes: final_fellows_set/ehf_fellow_profiles_demo_data.json
"""

import json
import re
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT = REPO_ROOT / "final_fellows_set" / "ehf_fellow_profiles_deduped.json"
OUTPUT = REPO_ROOT / "final_fellows_set" / "ehf_fellow_profiles_demo_data.json"
IMAGES_DIRS = [
    REPO_ROOT / "app" / "fellow_profile_images_by_name",
    REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name",
]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")


def build_image_index() -> set[str]:
    """Build a set of normalized image stems from available image directories."""
    stems = set()
    for d in IMAGES_DIRS:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                stems.add(p.stem.lower())
    return stems


def has_local_image(slug: str, image_stems: set[str]) -> bool:
    """Check if an image file exists for the given slug (exact or normalized match)."""
    if slug in image_stems:
        return True
    # Normalize both sides to strip all non-alnum to match server fallback logic
    slug_norm = re.sub(r"[^a-z0-9]", "", slug)
    return any(re.sub(r"[^a-z0-9]", "", s) == slug_norm for s in image_stems)


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        records = json.load(f)

    image_stems = build_image_index()
    if not image_stems:
        print("WARNING: No image files found in image directories")

    filtered = []
    skipped = []
    for r in records:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        slug = slugify(name)
        if has_local_image(slug, image_stems):
            filtered.append(r)
        else:
            skipped.append(name)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    print(f"Filtered {len(records)} -> {len(filtered)} records (removed {len(records) - len(filtered)})")
    if skipped:
        print(f"Skipped {len(skipped)} named fellows with no local image:")
        for name in skipped:
            print(f"  {name}")
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
