#!/usr/bin/env python3
"""Render the social share card (og:image) for the PolitiUpdate website.

The card is what Reddit, Facebook, LinkedIn and X show when a PolitiUpdate link
is shared. Without it every shared link renders as a small text-only card, which
measurably costs clicks — so it is part of the distribution pre-flight.

Output: website/og-image.png (1200x630, the size X/Facebook expect for a
"summary_large_image" / og:image card).

Run (Pillow is a build-time-only dependency, it is deliberately NOT in
requirements.txt because no service imports it):

    uv venv /tmp/ogvenv && uv pip install --python /tmp/ogvenv/bin/python pillow
    /tmp/ogvenv/bin/python scripts/make-og-image.py

Re-run it whenever the tagline or the handle in the card changes, then commit
website/og-image.png with the site.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1200, 630
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "website" / "og-image.png"

FONT_DIR = pathlib.Path("/usr/share/fonts/truetype/dejavu")
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"

BG_TOP = (7, 24, 39)
BG_BOTTOM = (14, 40, 63)
BRAND_BLUE = (11, 75, 190)
TEXT_MAIN = (248, 250, 252)
TEXT_BODY = (219, 231, 240)
TEXT_ACCENT = (125, 211, 252)
TEXT_MUTED = (148, 178, 205)

TITLE = "PolitiUpdate"
SUBTITLE = "Danmarks hurtigste opdateringer fra politiet"
FOOTER = "Uofficiel spejling af politiets officielle RSS-feed · @PolitiUpdate"


def _vertical_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        base.putpixel(
            (0, y),
            tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )
    return base.resize((width, height))


def _radial_glow(width: int, height: int, colour: tuple[int, int, int]) -> Image.Image:
    """A soft blue blob in the top-left, mimicking the site's radial-gradient."""
    glow = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-width * 0.25, -height * 0.9, width * 0.75, height * 0.9), fill=colour)
    return glow.filter(ImageFilter.GaussianBlur(140))


def _font(path: pathlib.Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def main() -> None:
    canvas = _vertical_gradient(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)
    canvas = Image.blend(canvas, _radial_glow(WIDTH, HEIGHT, (29, 78, 216)), 0.18)
    canvas = canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Brand mark: rounded blue square with three white bars (same motif as favicon.svg).
    mark = (76, 92, 172, 188)
    draw.rounded_rectangle(mark, radius=20, fill=BRAND_BLUE)
    for offset, bar_width in ((0, 14), (32, 14), (64, 22)):
        draw.rounded_rectangle(
            (mark[0] + 20 + offset, mark[1] + 24, mark[0] + 20 + offset + bar_width, mark[3] - 24),
            radius=5,
            fill=TEXT_MAIN,
        )

    draw.text((196, 104), TITLE, font=_font(FONT_BOLD, 96), fill=TEXT_MAIN)
    draw.text((80, 262), SUBTITLE, font=_font(FONT_REGULAR, 40), fill=TEXT_BODY)

    # Accent rule + topically scannable keywords (this is what a Danish reader
    # searching "efterlysning" or "savnet" recognises).
    draw.rectangle((80, 352, 300, 360), fill=BRAND_BLUE)
    draw.text((80, 396), "Efterlysninger · Anholdelser · Grundlovsforhør · Ugentligt overblik",
              font=_font(FONT_REGULAR, 30), fill=TEXT_ACCENT)

    draw.rectangle((0, HEIGHT - 96, WIDTH, HEIGHT - 88), fill=(11, 75, 190))
    draw.text((80, HEIGHT - 68), FOOTER, font=_font(FONT_REGULAR, 26), fill=TEXT_MUTED)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT_PATH, format="PNG", optimize=True)
    print(f"wrote {OUT_PATH} ({canvas.width}x{canvas.height}, {OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
