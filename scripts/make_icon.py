"""Draw the integration's brand icon: a house with a music note on an LED matrix.

    python scripts/make_icon.py

Writes custom_components/tuneshine/brand/icon.png (256px) and icon@2x.png (512px).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# 16x16 pixel art. H = house, N = music note, . = unlit.
ART = [
    "................",
    ".......HH.......",
    "......HHHH......",
    ".....HH..HH.....",
    "....HH....HH....",
    "...HH......HH...",
    "..HH...NNN..HH..",
    ".HH....N.NN..HH.",
    "..H....N..N..H..",
    "..H....N.....H..",
    "..H....N.....H..",
    "..H..NNN.....H..",
    "..H.NNNN.....H..",
    "..H..NN......H..",
    "..HHHHHHHHHHHH..",
    "................",
]

HOUSE_TOP, HOUSE_BOTTOM = (90, 230, 255), (40, 120, 255)
NOTE_TOP, NOTE_BOTTOM = (255, 210, 60), (255, 70, 170)
UNLIT = (28, 32, 52)
TILE_TOP, TILE_BOTTOM = (16, 20, 44), (34, 14, 58)


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def render(size: int) -> Image.Image:
    scale = 4
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    # Rounded tile with a vertical gradient.
    tile = Image.new("RGB", (big, big))
    draw = ImageDraw.Draw(tile)
    for y in range(big):
        draw.line((0, y, big, y), fill=mix(TILE_TOP, TILE_BOTTOM, y / big))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=255)
    image.paste(tile, (0, 0), mask)

    # LED dots, with a soft glow under the lit ones.
    margin = big * 0.12
    pitch = (big - 2 * margin) / 16
    radius = pitch * 0.38
    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dots = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    glow_draw, dot_draw = ImageDraw.Draw(glow), ImageDraw.Draw(dots)
    for row, line in enumerate(ART):
        for col, pixel in enumerate(line):
            cx = margin + (col + 0.5) * pitch
            cy = margin + (row + 0.5) * pitch
            t = row / 15
            if pixel == "H":
                color = mix(HOUSE_TOP, HOUSE_BOTTOM, t)
            elif pixel == "N":
                color = mix(NOTE_TOP, NOTE_BOTTOM, (row - 6) / 7)
            else:
                color = UNLIT
            box = (cx - radius, cy - radius, cx + radius, cy + radius)
            dot_draw.ellipse(box, fill=(*color, 255))
            if pixel != ".":
                r = radius * 1.9
                glow_draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(pitch * 0.45))
    image.alpha_composite(glow)
    image.alpha_composite(dots)

    # Keep everything inside the rounded tile.
    image.putalpha(Image.composite(image.getchannel("A"), Image.new("L", (big, big), 0), mask))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "custom_components" / "tuneshine" / "brand"
    out.mkdir(parents=True, exist_ok=True)
    render(256).save(out / "icon.png", optimize=True)
    render(512).save(out / "icon@2x.png", optimize=True)
    print(f"wrote {out}/icon.png and icon@2x.png")


if __name__ == "__main__":
    main()
