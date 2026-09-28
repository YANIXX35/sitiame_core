# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Regenerates the installable app's icons (sitiame_core/public/pwa/) from
the circular emblem of the logo -- the S in the gold arrows circle, left
part of public/images/sitiame-capital-logo.png. Run from the repo root:

    python scripts/make_pwa_icons.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "sitiame_core" / "public"
logo = Image.open(ROOT / "images" / "sitiame-capital-logo.png").convert("RGBA")
out = ROOT / "pwa"

# emblem = non-white, non-transparent pixels of the left 45% of the logo
left = logo.crop((0, 0, int(logo.width * 0.45), logo.height))
mask = Image.new("L", left.size, 0)
pixels, marks = left.load(), mask.load()
for x in range(left.width):
	for y in range(left.height):
		r, g, b, a = pixels[x, y]
		if a > 40 and min(r, g, b) < 225:
			marks[x, y] = 255
emblem = left.crop(mask.getbbox())


def icon(size, ratio):
	canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
	scale = size * ratio / max(emblem.size)
	art = emblem.resize((round(emblem.width * scale), round(emblem.height * scale)), Image.LANCZOS)
	canvas.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
	return canvas.convert("RGB")


icon(192, 0.86).save(out / "icon-192.png", optimize=True)
icon(512, 0.86).save(out / "icon-512.png", optimize=True)
# maskable: Android crops to a circle/squircle, the art must stay in the
# central safe zone
icon(512, 0.62).save(out / "icon-maskable-512.png", optimize=True)
icon(180, 0.86).save(out / "apple-touch-icon.png", optimize=True)
