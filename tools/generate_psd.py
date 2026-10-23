#!/usr/bin/env python3
"""Generate a simple PSD preview from an HTML source file."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def generate_psd(html_file: str, output_path: str = "phishing.psd") -> None:
    """Render the first lines of *html_file* into a PSD preview."""
    html = Path(html_file).read_text(encoding="utf-8")
    width, height = 800, 600
    image = Image.new("RGB", (width, height), color=(245, 245, 247))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 30), fill=(59, 89, 152))
    draw.text((10, 8), "iCloud Sync Error", fill="white")

    y = 50
    for line in html.splitlines()[:6]:
        draw.text((10, y), line.strip(), fill=(102, 102, 102))
        y += 30

    draw.rectangle((150, 80, 450, 120), outline="#ccc", width=2)
    draw.text((160, 95), "Enter Apple ID (e.g., user@example.com)", fill=(50, 50, 50))
    draw.rectangle((480, 70, 620, 130), fill="#007aff", outline="white")
    draw.text((505, 95), "Repair Now", fill="white")
    try:
        image.save(output_path, format="PSD")
    except (KeyError, ValueError) as exc:
        raise RuntimeError(
            "PSD export requires a Pillow build with PSD save support"
        ) from exc


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_psd.py <html_file> <output_psd>", file=sys.stderr)
        raise SystemExit(2)
    generate_psd(sys.argv[1], sys.argv[2])
