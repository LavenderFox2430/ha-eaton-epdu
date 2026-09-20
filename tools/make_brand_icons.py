#!/usr/bin/env python3
"""Generate the brand icons for this integration.

Draws `custom_components/eaton_epdu/brand/icon.png` (256x256) and
`icon@2x.png` (512x512) to the home-assistant/brands specification: square
PNG, transparent, trimmed to the artwork.

The artwork is original -- a generic rack PDU face with four receptacles --
deliberately *not* the Eaton logo, which is a trademark this repository has no
licence to redistribute. Replace these files if you have the rights to use the
manufacturer's mark.

Needs Pillow:  pip install pillow
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

#: Supersampling factor; the artwork is drawn large and downscaled to smooth it.
SUPERSAMPLE = 4

BODY = (38, 50, 56, 255)  # slate housing
BODY_EDGE = (69, 90, 100, 255)  # subtle bevel
FACE = (236, 239, 241, 255)  # receptacle face
SLOT = (38, 50, 56, 255)  # slot cut-outs
LED = (67, 200, 120, 255)  # status LED


def _receptacle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """Draw one NEMA-style receptacle centred on (cx, cy)."""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FACE)

    slot_w, slot_h = r * 0.26, r * 0.74
    slot_y = cy - r * 0.16
    for direction in (-1, 1):
        slot_x = cx + direction * r * 0.40
        draw.rounded_rectangle(
            (slot_x - slot_w / 2, slot_y - slot_h / 2, slot_x + slot_w / 2, slot_y + slot_h / 2),
            radius=slot_w / 2,
            fill=SLOT,
        )

    ground_r = r * 0.22
    ground_y = cy + r * 0.52
    draw.ellipse(
        (cx - ground_r, ground_y - ground_r, cx + ground_r, ground_y + ground_r),
        fill=SLOT,
    )


def build(size: int) -> Image.Image:
    """Render the icon at `size` x `size`."""
    scale = size * SUPERSAMPLE
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Housing fills the canvas so the artwork is trimmed, as brands requires.
    radius = scale * 0.19
    draw.rounded_rectangle((0, 0, scale - 1, scale - 1), radius=radius, fill=BODY)
    draw.rounded_rectangle(
        (0, 0, scale - 1, scale - 1),
        radius=radius,
        outline=BODY_EDGE,
        width=int(scale * 0.018),
    )

    # Four receptacles, 2 x 2.
    receptacle_r = scale * 0.175
    offset = scale * 0.235
    for row in (-1, 1):
        for column in (-1, 1):
            _receptacle(
                draw,
                scale / 2 + column * offset,
                scale / 2 + row * offset * 1.06,
                receptacle_r,
            )

    # Status LED in the corner, the way a real unit shows link state.
    led_r = scale * 0.032
    led_x = scale * 0.5
    led_y = scale * 0.5
    draw.ellipse((led_x - led_r, led_y - led_r, led_x + led_r, led_y + led_r), fill=LED)

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    """Write both icon sizes into the integration's brand directory."""
    target = Path(__file__).resolve().parent.parent / "custom_components" / "eaton_epdu" / "brand"
    target.mkdir(parents=True, exist_ok=True)
    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        path = target / name
        build(size).save(path, "PNG", optimize=True)
        print(f"wrote {path} ({size}x{size})")


if __name__ == "__main__":
    main()
