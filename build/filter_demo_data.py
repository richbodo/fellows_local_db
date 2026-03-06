#!/usr/bin/env python3
"""
Filter fellow profiles to only those with a name AND a local image file.
Reads:  final_fellows_set/ehf_fellow_profiles_deduped.json
Writes: final_fellows_set/ehf_fellow_profiles_demo_data.json
"""

import hashlib
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

# MD5 hashes of known placeholder images (grey background with white diamond logo)
PLACEHOLDER_HASHES = {
    "5aa43d100ed38aabebbd8393338e961d",
    "d01a4e3bd727674a2e698c18b61a63bb",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")


def find_image_path(slug: str) -> Path | None:
    """Return the image file path for a slug, or None if not found."""
    for d in IMAGES_DIRS:
        if not d.is_dir():
            continue
        for ext in (".jpg", ".jpeg", ".png"):
            p = d / f"{slug}{ext}"
            if p.is_file():
                return p
        # Fuzzy match: strip non-alnum like the server does
        slug_norm = re.sub(r"[^a-z0-9]", "", slug)
        for p in d.iterdir():
            if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            if re.sub(r"[^a-z0-9]", "", p.stem.lower()) == slug_norm:
                return p
    return None


def is_placeholder(image_path: Path) -> bool:
    """Return True if the image file matches a known placeholder hash."""
    md5 = hashlib.md5(image_path.read_bytes()).hexdigest()
    return md5 in PLACEHOLDER_HASHES


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        records = json.load(f)

    filtered = []
    skipped_no_image = []
    skipped_placeholder = []
    for r in records:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        slug = slugify(name)
        img = find_image_path(slug)
        if not img:
            skipped_no_image.append(name)
        elif is_placeholder(img):
            skipped_placeholder.append(name)
        else:
            filtered.append(r)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    total_skipped = len(skipped_no_image) + len(skipped_placeholder)
    print(f"Filtered {len(records)} -> {len(filtered)} records (removed {total_skipped})")
    if skipped_no_image:
        print(f"Skipped {len(skipped_no_image)} fellows with no local image:")
        for name in skipped_no_image:
            print(f"  {name}")
    if skipped_placeholder:
        print(f"Skipped {len(skipped_placeholder)} fellows with placeholder image:")
        for name in skipped_placeholder:
            print(f"  {name}")
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
