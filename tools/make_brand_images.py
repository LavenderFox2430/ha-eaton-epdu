#!/usr/bin/env python3
"""Generate the brand images for this integration.

Writes into `custom_components/eaton_epdu/brand/`, to the home-assistant/brands
specification:

    icon.png      256 x 256   square
    icon@2x.png   512 x 512
    logo.png      shortest side 256, landscape, trimmed
    logo@2x.png   shortest side 512

Two source images are vendored alongside this script:

`epdu_favicon_source.png` -- the favicon an ePDU G3 serves from its own web
interface (the "E" badge), extracted from the `<link rel="icon">` data URI on
`http://<pdu>/`. It is 64x64, so the icons are upscaled; that is soft at full
size but fine at the sizes Home Assistant renders an icon.

`eaton_logo_source.png` -- the Eaton wordmark from Wikimedia Commons
(File:2017 Eaton logo.png), which Commons hosts as public domain because a
plain text wordmark falls below the threshold of originality.

Both are Eaton trademarks, used to identify the hardware this integration
talks to; see the trademark note in README.md. Neither is recoloured or
redrawn -- only trimmed and scaled.

    --icon-style favicon    (default) the ePDU's own E badge
    --icon-style wordmark   the EATON wordmark, letterboxed into the square
    --icon-style letter     just the leading E of the wordmark

Needs Pillow:  pip install pillow
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

#: Standard and hDPI sizes for the square icon.
ICON_SIZES = ((256, "icon.png"), (512, "icon@2x.png"))
#: Shortest-side targets for the landscape logo.
LOGO_SHORT_SIDES = ((256, "logo.png"), (512, "logo@2x.png"))
#: Fraction of the icon canvas left empty around a mark that is not already
#: drawn as an icon. The favicon needs none: it fills its own canvas.
ICON_MARGIN = 0.06

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
FAVICON_SOURCE = TOOLS / "epdu_favicon_source.png"
LOGO_SOURCE = TOOLS / "eaton_logo_source.png"
TARGET = ROOT / "custom_components" / "eaton_epdu" / "brand"


def _blank_runs(image: Image.Image, axis: str) -> list[tuple[int, int]]:
    """Find the runs of fully transparent rows (or columns) inside the artwork."""
    alpha = image.split()[3]
    width, height = image.size
    if axis == "rows":
        counts = [
            (y, sum(1 for x in range(0, width, 2) if alpha.getpixel((x, y)) > 20))
            for y in range(height)
        ]
    else:
        counts = [
            (x, sum(1 for y in range(0, height, 2) if alpha.getpixel((x, y)) > 20))
            for x in range(width)
        ]
    ink = [i for i, c in counts if c > 0]
    if not ink:
        return []
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(ink[0], ink[-1] + 1):
        if counts[i][1] == 0 and start is None:
            start = i
        elif counts[i][1] > 0 and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def wordmark(source: Image.Image) -> Image.Image:
    """Crop the EATON wordmark, dropping the tagline below it."""
    trimmed = source.crop(source.getbbox())
    gaps = _blank_runs(trimmed, "rows")
    if gaps:
        # The widest horizontal gap separates the wordmark from the tagline.
        split = max(gaps, key=lambda run: run[1] - run[0])[0]
        trimmed = trimmed.crop((0, 0, trimmed.width, split))
    return trimmed.crop(trimmed.getbbox())


def leading_letter(mark: Image.Image) -> Image.Image:
    """Crop the leading E of the wordmark."""
    gaps = _blank_runs(mark, "columns")
    if gaps:
        mark = mark.crop((0, 0, gaps[0][0], mark.height))
    return mark.crop(mark.getbbox())


def square(mark: Image.Image, size: int, margin: float) -> Image.Image:
    """Centre the mark on a transparent square canvas."""
    usable = int(size * (1 - 2 * margin))
    scale = min(usable / mark.width, usable / mark.height)
    scaled = mark.resize(
        (max(1, round(mark.width * scale)), max(1, round(mark.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2), scaled)
    return canvas


def landscape(mark: Image.Image, short_side: int) -> Image.Image:
    """Scale the trimmed logo so its shortest side is `short_side`."""
    scale = short_side / min(mark.width, mark.height)
    return mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)


def icon_artwork(style: str) -> tuple[Image.Image, float]:
    """Return the artwork for the square icon, and the margin it wants."""
    if style == "favicon":
        # Already drawn as an icon, bleeding to the edge of its own canvas.
        return Image.open(FAVICON_SOURCE).convert("RGBA"), 0.0
    mark = wordmark(Image.open(LOGO_SOURCE).convert("RGBA"))
    return (leading_letter(mark) if style == "letter" else mark), ICON_MARGIN


def main() -> None:
    """Write all four brand images."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--icon-style", choices=("favicon", "wordmark", "letter"), default="favicon"
    )
    args = parser.parse_args()

    TARGET.mkdir(parents=True, exist_ok=True)

    art, margin = icon_artwork(args.icon_style)
    for size, name in ICON_SIZES:
        path = TARGET / name
        square(art, size, margin).save(path, "PNG", optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({size}x{size}, {args.icon_style})")

    full = Image.open(LOGO_SOURCE).convert("RGBA")
    full = full.crop(full.getbbox())
    for short_side, name in LOGO_SHORT_SIDES:
        path = TARGET / name
        image = landscape(full, short_side)
        image.save(path, "PNG", optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({image.width}x{image.height}, wordmark)")


if __name__ == "__main__":
    main()
