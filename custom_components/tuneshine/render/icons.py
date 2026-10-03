"""Shaded weather icons.

Icons are drawn on a 4x oversized RGBA canvas in a 32-unit coordinate space,
with gradient fills, outlines and highlights, then downsampled so curves come
out smooth on the 64x64 matrix.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .font import Color
from .style import gradient

UNITS = 32
FACTOR = 4
OUTLINE: Color = (12, 18, 36)

Canvas = Image.Image


class Pen:
    """Draws in 32-unit coordinates onto a supersampled canvas."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.px = size * FACTOR / UNITS
        self.canvas = Image.new("RGBA", (size * FACTOR, size * FACTOR), (0, 0, 0, 0))

    def s(self, value: float) -> float:
        return value * self.px

    def box(self, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (self.s(x0), self.s(y0), self.s(x1), self.s(y1))

    def mask(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        mask = Image.new("L", self.canvas.size, 0)
        return mask, ImageDraw.Draw(mask)

    def fill(
        self,
        mask: Image.Image,
        top: Color,
        bottom: Color,
        *,
        outline: Color | None = OUTLINE,
        outline_width: float = 1.2,
        alpha: int = 255,
    ) -> None:
        """Paint a vertical gradient through a mask, with an optional outline."""
        bbox = mask.getbbox()
        if bbox is None:
            return
        if outline is not None:
            grow = int(self.s(outline_width)) * 2 + 1
            ring = mask.filter(ImageFilter.MaxFilter(grow))
            self._paint(ring, Image.new("RGB", self.canvas.size, outline), alpha)
        fill = Image.new("RGB", self.canvas.size, bottom)
        height = bbox[3] - bbox[1]
        fill.paste(gradient((self.canvas.width, height), top, bottom), (0, bbox[1]))
        self._paint(mask, fill, alpha)

    def _paint(self, mask: Image.Image, fill: Image.Image, alpha: int) -> None:
        if alpha < 255:
            mask = mask.point(lambda v: v * alpha // 255)
        layer = fill.convert("RGBA")
        layer.putalpha(mask)
        self.canvas.alpha_composite(layer)

    def result(self) -> Image.Image:
        return self.canvas.resize((self.size, self.size), Image.Resampling.LANCZOS)


# ------------------------------------------------------------------ shapes


def _sun(pen: Pen, cx: float = 16, cy: float = 16, r: float = 7.5, rays: bool = True) -> None:
    glow, draw = pen.mask()
    draw.ellipse(pen.box(cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5), fill=255)
    pen.fill(
        glow.filter(ImageFilter.GaussianBlur(pen.s(2))),
        (255, 170, 0),
        (255, 120, 0),
        outline=None,
        alpha=90,
    )
    if rays:
        rays_mask, draw = pen.mask()
        for i in range(8):
            angle = math.radians(i * 45 + 22.5)
            inner, outer, half = r + 2.2, r + 6.2, 0.38
            points = [
                (cx + math.cos(angle - half) * inner, cy + math.sin(angle - half) * inner),
                (cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
                (cx + math.cos(angle + half) * inner, cy + math.sin(angle + half) * inner),
            ]
            draw.polygon([(pen.s(x), pen.s(y)) for x, y in points], fill=255)
        pen.fill(rays_mask, (255, 230, 80), (255, 140, 0), outline_width=0.8)
    disc, draw = pen.mask()
    draw.ellipse(pen.box(cx - r, cy - r, cx + r, cy + r), fill=255)
    pen.fill(disc, (255, 248, 150), (255, 150, 0))
    shine, draw = pen.mask()
    draw.ellipse(pen.box(cx - r * 0.55, cy - r * 0.6, cx - r * 0.05, cy - r * 0.15), fill=255)
    pen.fill(shine, (255, 255, 230), (255, 255, 200), outline=None, alpha=170)


def _cloud(
    pen: Pen,
    ox: float = 0,
    oy: float = 0,
    scale: float = 1.0,
    top: Color = (255, 255, 255),
    bottom: Color = (165, 185, 215),
) -> None:
    def b(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return pen.box(ox + x0 * scale, oy + y0 * scale, ox + x1 * scale, oy + y1 * scale)

    mask, draw = pen.mask()
    draw.ellipse(b(2, 13, 14, 25), fill=255)
    draw.ellipse(b(8, 6, 22, 20), fill=255)
    draw.ellipse(b(17, 11, 29, 23), fill=255)
    draw.rounded_rectangle(b(6, 16, 26, 25), radius=pen.s(3 * scale), fill=255)
    pen.fill(mask, top, bottom)


def _drop(pen: Pen, x: float, y: float, size: float = 1.0) -> None:
    mask, draw = pen.mask()
    r = 1.6 * size
    draw.ellipse(pen.box(x - r, y, x + r, y + 2 * r), fill=255)
    draw.polygon(
        [
            (pen.s(x - r * 0.95), pen.s(y + r * 0.8)),
            (pen.s(x + 0.6 * size), pen.s(y - 2.4 * size)),
            (pen.s(x + r * 0.95), pen.s(y + r * 0.8)),
        ],
        fill=255,
    )
    pen.fill(mask, (170, 230, 255), (20, 110, 255), outline_width=0.6)


def _flake(pen: Pen, x: float, y: float, r: float = 2.6) -> None:
    mask, draw = pen.mask()
    width = max(1, int(pen.s(0.9)))
    for i in range(3):
        angle = math.radians(i * 60 + 90)
        dx, dy = math.cos(angle) * r, math.sin(angle) * r
        draw.line(
            (pen.s(x - dx), pen.s(y - dy), pen.s(x + dx), pen.s(y + dy)), fill=255, width=width
        )
    draw.ellipse(pen.box(x - 0.9, y - 0.9, x + 0.9, y + 0.9), fill=255)
    pen.fill(mask, (255, 255, 255), (180, 225, 255), outline_width=0.6)


def _bolt(pen: Pen, ox: float = 0, oy: float = 0) -> None:
    mask, draw = pen.mask()
    points = [(17, 15), (10.5, 23), (14.5, 23), (12, 31), (21, 20.5), (16.5, 20.5), (19.5, 15)]
    draw.polygon([(pen.s(ox + x), pen.s(oy + y)) for x, y in points], fill=255)
    pen.fill(mask, (255, 255, 160), (255, 170, 0), outline=(120, 50, 0), outline_width=0.8)


def _stars(pen: Pen, positions: list[tuple[float, float, float]]) -> None:
    mask, draw = pen.mask()
    for x, y, r in positions:
        draw.polygon(
            [
                (pen.s(x), pen.s(y - r)),
                (pen.s(x + r * 0.3), pen.s(y - r * 0.3)),
                (pen.s(x + r), pen.s(y)),
                (pen.s(x + r * 0.3), pen.s(y + r * 0.3)),
                (pen.s(x), pen.s(y + r)),
                (pen.s(x - r * 0.3), pen.s(y + r * 0.3)),
                (pen.s(x - r), pen.s(y)),
                (pen.s(x - r * 0.3), pen.s(y - r * 0.3)),
            ],
            fill=255,
        )
    pen.fill(mask, (255, 255, 220), (255, 230, 150), outline=None)


# ------------------------------------------------------------------- icons


def sunny(pen: Pen) -> None:
    _sun(pen)


def clear_night(pen: Pen) -> None:
    _stars(pen, [(5, 7, 2.2), (26, 25, 1.8), (27, 6, 1.4), (7, 26, 1.2)])
    disc, draw = pen.mask()
    draw.ellipse(pen.box(7, 6, 25, 24), fill=255)
    cut, draw = pen.mask()
    draw.ellipse(pen.box(13, 2, 30, 19), fill=255)
    crescent = ImageChops.subtract(disc, cut)
    pen.fill(crescent, (255, 250, 210), (235, 195, 110))
    craters, draw = pen.mask()
    draw.ellipse(pen.box(10.5, 15, 13, 17.5), fill=255)
    draw.ellipse(pen.box(14, 19.5, 15.8, 21.3), fill=255)
    pen.fill(ImageChops.multiply(craters, crescent), (215, 180, 110), (200, 160, 90), outline=None)


def partly_cloudy(pen: Pen) -> None:
    _sun(pen, cx=11, cy=11, r=6)
    _cloud(pen, ox=5, oy=6, scale=0.85)


def partly_cloudy_night(pen: Pen) -> None:
    disc, draw = pen.mask()
    draw.ellipse(pen.box(3, 3, 17, 17), fill=255)
    cut, draw = pen.mask()
    draw.ellipse(pen.box(8, 0, 21, 13), fill=255)
    pen.fill(ImageChops.subtract(disc, cut), (255, 250, 210), (235, 195, 110))
    _stars(pen, [(24, 5, 1.6)])
    _cloud(pen, ox=5, oy=6, scale=0.85)


def cloudy(pen: Pen) -> None:
    _cloud(pen, ox=-3, oy=-3, scale=0.8, top=(170, 180, 200), bottom=(105, 115, 140))
    _cloud(pen, ox=3, oy=4, scale=0.9)


def fog(pen: Pen) -> None:
    _cloud(pen, ox=2, oy=-4, scale=0.85, top=(200, 210, 225), bottom=(140, 150, 175))
    mask, draw = pen.mask()
    for y, x0, x1 in ((19.5, 3, 25), (23.5, 7, 29), (27.5, 2, 22)):
        draw.rounded_rectangle(pen.box(x0, y, x1, y + 2.2), radius=pen.s(1.1), fill=255)
    pen.fill(mask, (235, 240, 250), (180, 190, 210), outline_width=0.6)


def rainy(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-4, scale=0.95)
    for x, y in ((9, 23), (16, 26), (23, 23)):
        _drop(pen, x, y)


def pouring(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95, top=(185, 195, 215), bottom=(105, 115, 145))
    for x, y in ((6, 22), (12, 26), (18, 22), (24, 26), (15, 18.5)):
        _drop(pen, x, y, 0.85)


def snowy(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95)
    for x, y in ((8, 24), (16, 28), (24, 24)):
        _flake(pen, x, y)


def snowy_rainy(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95)
    _flake(pen, 9, 24)
    _drop(pen, 16, 25)
    _flake(pen, 23, 25)


def hail(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95, top=(185, 195, 215), bottom=(105, 115, 145))
    mask, draw = pen.mask()
    for x, y in ((8, 23), (15, 27), (22, 23), (19, 29.5)):
        draw.ellipse(pen.box(x - 1.8, y - 1.8, x + 1.8, y + 1.8), fill=255)
    pen.fill(mask, (255, 255, 255), (150, 200, 240), outline_width=0.6)


def lightning(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95, top=(150, 155, 185), bottom=(80, 80, 115))
    _bolt(pen, ox=0, oy=-1)


def lightning_rainy(pen: Pen) -> None:
    _cloud(pen, ox=1, oy=-5, scale=0.95, top=(150, 155, 185), bottom=(80, 80, 115))
    _drop(pen, 6.5, 23, 0.85)
    _drop(pen, 25, 24, 0.85)
    _bolt(pen, ox=0, oy=-1)


def windy(pen: Pen) -> None:
    mask, draw = pen.mask()
    width = int(pen.s(2.2))
    draw.line((pen.s(2), pen.s(11), pen.s(20), pen.s(11)), fill=255, width=width)
    draw.arc(pen.box(16, 4, 26, 13), 160, 90, fill=255, width=width)
    draw.line((pen.s(2), pen.s(17), pen.s(27), pen.s(17)), fill=255, width=width)
    draw.line((pen.s(5), pen.s(23), pen.s(17), pen.s(23)), fill=255, width=width)
    draw.arc(pen.box(13, 21, 23, 30), 270, 200, fill=255, width=width)
    pen.fill(mask, (220, 255, 255), (90, 210, 240), outline_width=0.7)


def exceptional(pen: Pen) -> None:
    mask, draw = pen.mask()
    draw.polygon([(pen.s(16), pen.s(3)), (pen.s(30), pen.s(28)), (pen.s(2), pen.s(28))], fill=255)
    pen.fill(mask.filter(ImageFilter.MaxFilter(5)), (255, 200, 40), (255, 60, 30))
    mark, draw = pen.mask()
    draw.rounded_rectangle(pen.box(14.6, 11, 17.4, 21), radius=pen.s(1.2), fill=255)
    draw.ellipse(pen.box(14.5, 22.5, 17.5, 25.5), fill=255)
    pen.fill(mark, (60, 10, 0), (60, 10, 0), outline=None)


ICONS: dict[str, Callable[[Pen], None]] = {
    "clear-night": clear_night,
    "cloudy": cloudy,
    "exceptional": exceptional,
    "fog": fog,
    "hail": hail,
    "lightning": lightning,
    "lightning-rainy": lightning_rainy,
    "partlycloudy": partly_cloudy,
    "partlycloudy-night": partly_cloudy_night,
    "pouring": pouring,
    "rainy": rainy,
    "snowy": snowy,
    "snowy-rainy": snowy_rainy,
    "sunny": sunny,
    "windy": windy,
    "windy-variant": windy,
}


def render_icon(condition: str | None, size: int = 32) -> Image.Image:
    """An RGBA icon for a Home Assistant weather condition."""
    pen = Pen(size)
    ICONS.get(condition or "", cloudy)(pen)
    return pen.result()
