#!/usr/bin/env python3
"""Generate a simple BK FIRE placeholder logo (replace with official artwork)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo.png"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    w, h = 320, 120
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Ember bar
    draw.rounded_rectangle([0, 10, w - 1, h - 11], radius=12, fill=(155, 34, 38, 255))
    draw.rounded_rectangle([6, 16, w - 7, h - 17], radius=8, fill=(232, 93, 4, 255))

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 48)
    except OSError:
        font = ImageFont.load_default()

    text = "BK FIRE"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2, (h - th) / 2 - 4), text, fill=(255, 247, 240, 255), font=font)

    img.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
