#!/usr/bin/env python3
"""Build sharp PNGs under public/icons/ from public/favicon.png for Outlook manifests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "public" / "favicon.png"
OUT_DIR = ROOT / "public" / "icons"
# Ribbon/command surfaces need exact 16 / 32 / 80. Mail add-in manifest: IconUrl 64×64,
# HighResolutionIconUrl 128×128 (Microsoft Learn). Extra sizes are optional assets.
SIZES = (16, 32, 64, 80, 128, 192, 256, 512)


def downscale_square(img: Image.Image, size: int) -> Image.Image:
    """Multi-step LANCZOS downscale (better than one jump from ~1k px to 16)."""
    img = img.convert("RGBA")
    cur = img.size[0]
    if cur == size:
        return img
    while cur > max(size * 2, size):
        nxt = max(cur // 2, size)
        if nxt >= cur:
            break
        img = img.resize((nxt, nxt), Image.Resampling.LANCZOS)
        cur = nxt
    if cur != size:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source: {SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = Image.open(SRC)
    w, h = raw.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    square = raw.crop((left, top, left + side, top + side))

    for sz in SIZES:
        out = downscale_square(square, sz)
        dest = OUT_DIR / f"icon{sz}.png"
        out.save(dest, format="PNG", compress_level=6)
        print("wrote", dest)


if __name__ == "__main__":
    main()
