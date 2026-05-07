#!/usr/bin/env python3
"""Generate the PWA icon set from app/static/icons/donut-ehf.svg.

Outputs (all written to app/static/icons/):
  icon-192.png            transparent, 192x192 — manifest "any"
  icon-512.png            transparent, 512x512 — manifest "any"
  icon-maskable-192.png   opaque cream bg, 192x192, donut in 80% safe zone
  icon-maskable-512.png   opaque cream bg, 512x512, donut in 80% safe zone
  icon-180.png            transparent, 180x180 — apple-touch-icon
  favicon-32.png          transparent, 32x32  — browser tab
  favicon-16.png          transparent, 16x16  — browser tab

Run from repo root:
  .venv/bin/python build/generate_icons.py
"""

import io
import os
import sys
from pathlib import Path

# cairocffi can't find Homebrew's libcairo via dyld defaults on macOS;
# point it at the brewed prefix before importing cairosvg.
if sys.platform == "darwin":
    for _dir in ("/opt/homebrew/lib", "/usr/local/lib"):
        if Path(_dir, "libcairo.2.dylib").is_file():
            _existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                _dir + (":" + _existing if _existing else "")
            )
            break

import cairosvg  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_SVG = REPO_ROOT / "app" / "static" / "icons" / "donut-ehf.svg"
OUT_DIR = REPO_ROOT / "app" / "static" / "icons"

CREAM = (240, 230, 206, 255)
TEXT_RGBA = (240, 230, 206, 255)
SAFE_ZONE_RATIO = 0.80

# Donut hole geometry from the SVG viewBox 0 0 260 260
HOLE_CX = 130
HOLE_CY = 128
HOLE_R = 40
VIEWBOX = 260

FONT_CANDIDATES = [
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/Library/Fonts/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
]


def load_bold_font(size_px: int) -> ImageFont.ImageFont:
    for path, idx in FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size_px, index=idx)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def render_donut(size: int) -> Image.Image:
    png = cairosvg.svg2png(
        url=str(SRC_SVG), output_width=size, output_height=size
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


def overlay_ehf(img: Image.Image) -> Image.Image:
    """Stamp 'EHF' inside the donut hole using a system bold sans font.

    cairosvg's text rendering depends on fontconfig and is unreliable
    across machines, so we draw the text in Pillow against the rasterized
    donut. Coordinates scale from the SVG viewBox to pixel space.
    """
    w, _ = img.size
    scale = w / VIEWBOX
    cx = round(HOLE_CX * scale)
    cy = round(HOLE_CY * scale)
    hole_diameter_px = round(2 * HOLE_R * scale)

    # Pick the largest font size where "EHF" fits inside ~85% of the hole.
    text = "EHF"
    target_w = hole_diameter_px * 0.85
    target_h = hole_diameter_px * 0.7
    lo, hi = 4, max(8, hole_diameter_px)
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        font = load_bold_font(mid)
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= target_w and th <= target_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    font = load_bold_font(best)
    draw = ImageDraw.Draw(img)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=TEXT_RGBA)
    return img


def render_transparent(size: int) -> Image.Image:
    return overlay_ehf(render_donut(size))


def render_maskable(size: int) -> Image.Image:
    inner = round(size * SAFE_ZONE_RATIO)
    donut = render_transparent(inner)
    canvas = Image.new("RGBA", (size, size), CREAM)
    pad = (size - inner) // 2
    canvas.alpha_composite(donut, (pad, pad))
    return canvas


def main() -> int:
    if not SRC_SVG.is_file():
        print(f"Missing source SVG: {SRC_SVG}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", render_transparent(192)),
        ("icon-512.png", render_transparent(512)),
        ("icon-maskable-192.png", render_maskable(192)),
        ("icon-maskable-512.png", render_maskable(512)),
        ("icon-180.png", render_transparent(180)),
        ("favicon-32.png", render_transparent(32)),
        ("favicon-16.png", render_transparent(16)),
    ]
    for name, img in targets:
        path = OUT_DIR / name
        img.save(path, "PNG", optimize=True)
        print(f"  wrote {path.relative_to(REPO_ROOT)}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
