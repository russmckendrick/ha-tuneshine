"""Colour, gradient and text-effect helpers shared by the pages."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from PIL import Image, ImageDraw

from .font import Color, PixelFont

SIZE = 64
SHADOW: Color = (0, 0, 0)


@dataclass(frozen=True)
class Theme:
    """A background gradient plus the colours drawn on top of it."""

    bg_top: Color
    bg_bottom: Color
    text_top: Color
    text_bottom: Color
    accent: Color
    muted: Color


# Clock themes, keyed by the hour they start at.
TIME_THEMES: list[tuple[int, Theme]] = [
    (
        0,
        Theme(
            (4, 4, 26),
            (24, 6, 52),
            (150, 170, 255),
            (190, 90, 255),
            (120, 200, 255),
            (110, 110, 170),
        ),
    ),
    (
        5,
        Theme(
            (26, 8, 40),
            (70, 20, 30),
            (255, 220, 120),
            (255, 110, 90),
            (255, 150, 200),
            (200, 140, 150),
        ),
    ),
    (
        8,
        Theme(
            (0, 22, 54),
            (0, 52, 74),
            (255, 255, 255),
            (90, 220, 255),
            (255, 200, 40),
            (130, 190, 220),
        ),
    ),
    (
        12,
        Theme(
            (0, 30, 60),
            (0, 60, 66),
            (255, 250, 200),
            (255, 190, 40),
            (90, 230, 255),
            (140, 200, 210),
        ),
    ),
    (
        17,
        Theme(
            (40, 8, 46),
            (80, 24, 20),
            (255, 230, 140),
            (255, 90, 60),
            (255, 120, 200),
            (210, 150, 160),
        ),
    ),
    (
        21,
        Theme(
            (10, 4, 34),
            (34, 4, 48),
            (210, 160, 255),
            (255, 80, 180),
            (140, 120, 255),
            (140, 110, 180),
        ),
    ),
]

# Rotating palettes for text pages so each one has its own colour.
PAGE_THEMES: list[Theme] = [
    Theme(
        (0, 26, 52), (0, 54, 60), (255, 255, 255), (80, 230, 255), (0, 200, 255), (140, 200, 220)
    ),
    Theme(
        (40, 6, 46), (70, 10, 40), (255, 240, 255), (255, 110, 210), (255, 70, 170), (220, 150, 200)
    ),
    Theme(
        (6, 34, 14), (14, 54, 24), (240, 255, 220), (120, 255, 110), (90, 230, 80), (160, 210, 150)
    ),
    Theme(
        (52, 22, 0), (64, 10, 10), (255, 250, 210), (255, 170, 40), (255, 140, 0), (220, 180, 140)
    ),
    Theme(
        (14, 10, 50),
        (34, 10, 66),
        (230, 230, 255),
        (150, 130, 255),
        (140, 110, 255),
        (170, 160, 220),
    ),
]


def time_theme(hour: int) -> Theme:
    """The clock theme for an hour of the day."""
    theme = TIME_THEMES[0][1]
    for start, candidate in TIME_THEMES:
        if hour >= start:
            theme = candidate
    return theme


def mix(a: Color, b: Color, t: float) -> Color:
    """Linear blend between two colours."""
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def scale_color(color: Color, factor: float) -> Color:
    """Brighten or darken a colour."""
    return tuple(max(0, min(255, round(c * factor))) for c in color)  # type: ignore[return-value]


def gradient(size: tuple[int, int], top: Color, bottom: Color) -> Image.Image:
    """A vertical gradient."""
    width, height = size
    column = Image.new("RGB", (1, height))
    for y in range(height):
        column.putpixel((0, y), mix(top, bottom, y / max(height - 1, 1)))
    return column.resize((width, height), Image.Resampling.NEAREST)


def background(theme: Theme) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A 64x64 frame filled with the theme's background gradient."""
    image = gradient((SIZE, SIZE), theme.bg_top, theme.bg_bottom)
    return image, ImageDraw.Draw(image)


def temperature_color(value: float | None) -> tuple[Color, Color]:
    """Gradient colours for a temperature in °C: icy blue through to hot red."""
    stops: list[tuple[float, Color]] = [
        (-10, (170, 220, 255)),
        (0, (110, 200, 255)),
        (10, (120, 255, 200)),
        (18, (255, 240, 120)),
        (25, (255, 170, 50)),
        (32, (255, 70, 50)),
    ]
    if value is None:
        return (220, 220, 220), (160, 160, 160)
    if value <= stops[0][0]:
        base = stops[0][1]
    elif value >= stops[-1][0]:
        base = stops[-1][1]
    else:
        base = stops[0][1]
        for (t0, c0), (t1, c1) in pairwise(stops):
            if t0 <= value <= t1:
                base = mix(c0, c1, (value - t0) / (t1 - t0))
                break
    return mix(base, (255, 255, 255), 0.45), base


def text(
    image: Image.Image,
    font: PixelFont,
    xy: tuple[int, int],
    value: str,
    top: Color,
    bottom: Color | None = None,
    *,
    scale: tuple[int, int] = (1, 1),
    bold: bool = True,
    shadow: bool = True,
) -> int:
    """Draw gradient-filled text with a drop shadow. Returns its width."""
    mask = font.mask(value, scale, bold)
    x, y = xy
    if shadow:
        offset = max(1, scale[1] // 2)
        image.paste(SHADOW, (x + 1, y + offset), mask)
    fill = gradient(mask.size, top, bottom or top)
    # Keep the gradient across the cap height, not the descender row.
    if bottom and bottom != top:
        cap = font.height * scale[1]
        fill = gradient((mask.width, cap), top, bottom).crop((0, 0, mask.width, mask.height))
        fill.paste(bottom, (0, cap, mask.width, mask.height))
    image.paste(fill, (x, y), mask)
    return mask.width


def centered_text(
    image: Image.Image,
    font: PixelFont,
    y: int,
    value: str,
    top: Color,
    bottom: Color | None = None,
    *,
    scale: tuple[int, int] = (1, 1),
    bold: bool = True,
    shadow: bool = True,
    width: int = SIZE,
    x0: int = 0,
) -> None:
    """Gradient text centred in a horizontal span."""
    text_width = font.text_width(value, scale[0], bold)
    text(
        image,
        font,
        (x0 + (width - text_width) // 2, y),
        value,
        top,
        bottom,
        scale=scale,
        bold=bold,
        shadow=shadow,
    )


def pill(
    image: Image.Image,
    font: PixelFont,
    y: int,
    value: str,
    fill: Color,
    ink: Color = (0, 0, 0),
    *,
    bold: bool = False,
) -> None:
    """A rounded label, centred, like a tag."""
    draw = ImageDraw.Draw(image)
    width = font.text_width(value, 1, bold) + 6
    height = font.height + 4
    x = (SIZE - width) // 2
    draw.rounded_rectangle((x, y, x + width - 1, y + height - 1), radius=2, fill=fill)
    font.draw(draw, (x + 3, y + 2), value, ink, bold=bold)


def supersample(size: int, factor: int = 4) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A transparent oversized canvas for smooth icon drawing."""
    canvas = Image.new("RGBA", (size * factor, size * factor), (0, 0, 0, 0))
    return canvas, ImageDraw.Draw(canvas)


def downsample(canvas: Image.Image, size: int) -> Image.Image:
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def radial(size: int, inner: Color, outer: Color) -> Image.Image:
    """A square radial gradient, for spheres and glows."""
    image = Image.new("RGB", (size, size))
    centre = (size - 1) / 2
    max_d = math.hypot(centre, centre) * 0.75
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - centre * 0.8, y - centre * 0.8) / max_d
            pixels[x, y] = mix(inner, outer, d)
    return image


def fit_text(font: PixelFont, value: str, max_width: int = SIZE, bold: bool = False) -> str:
    """Truncate text so it fits within max_width pixels."""
    while value and font.text_width(value, bold=bold) > max_width:
        value = value[:-1]
    return value
