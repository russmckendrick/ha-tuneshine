"""Shaded weather icons.

Icons are drawn on a 4x oversized RGBA canvas in a 32-unit coordinate space,
with gradient fills, outlines and highlights, then downsampled so curves come
out smooth on the 64x64 matrix.

Every icon takes a loop position ``t`` in [0, 1). Motion only uses whole
cycles of ``t``, so frame 0 follows on from the last frame without a jump.
``t=None`` draws the still icon, exactly as it looked before icons moved.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .font import Color
from .style import gradient, mix

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


# ------------------------------------------------------------------ motion


def _wave(t: float | None, phase: float = 0.0, cycles: int = 1) -> float:
    """A sine in [-1, 1] that completes whole cycles over the loop; 0 when still."""
    if t is None:
        return 0.0
    return math.sin(2 * math.pi * (cycles * t + phase))


def _fall(
    t: float | None, still: float, phase: float, cycles: int, top: float, bottom: float
) -> tuple[float, int]:
    """Position and alpha of something falling from top to bottom, fading out at the end.

    The still icon has it resting at still, fully opaque.
    """
    if t is None:
        return still, 255
    progress = (cycles * t + phase) % 1.0
    alpha = 255 if progress < 0.7 else round(255 * (1 - progress) / 0.3)
    return top + (bottom - top) * progress, alpha


def flash(condition: str | None, t: float) -> float:
    """How bright a lightning strike is at t: 0 for none, 1 at its peak."""
    if condition not in ("lightning", "lightning-rainy"):
        return 0.0
    level = 0.0
    for start, peak in ((0.40, 1.0), (0.50, 0.7)):
        since = t - start
        if 0 <= since < 0.1:
            level = max(level, peak * (1 - since / 0.1))
    return level


# ------------------------------------------------------------------ shapes


def _sun(
    pen: Pen,
    cx: float = 16,
    cy: float = 16,
    r: float = 7.5,
    rays: bool = True,
    spin: float = 0.0,
    glow: float = 1.0,
) -> None:
    glow_mask, draw = pen.mask()
    draw.ellipse(pen.box(cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5), fill=255)
    pen.fill(
        glow_mask.filter(ImageFilter.GaussianBlur(pen.s(2))),
        (255, 170, 0),
        (255, 120, 0),
        outline=None,
        alpha=round(90 * glow),
    )
    if rays:
        rays_mask, draw = pen.mask()
        for i in range(8):
            # One loop turns the rays by one ray's spacing, so it repeats cleanly.
            angle = math.radians(i * 45 + 22.5 + spin * 45)
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


def _moon(pen: Pen, disc_box: tuple, cut_box: tuple) -> Image.Image:
    disc, draw = pen.mask()
    draw.ellipse(pen.box(*disc_box), fill=255)
    cut, draw = pen.mask()
    draw.ellipse(pen.box(*cut_box), fill=255)
    crescent = ImageChops.subtract(disc, cut)
    pen.fill(crescent, (255, 250, 210), (235, 195, 110))
    return crescent


def _cloud(
    pen: Pen,
    ox: float = 0,
    oy: float = 0,
    scale: float = 1.0,
    top: Color = (255, 255, 255),
    bottom: Color = (165, 185, 215),
    alpha: int = 255,
) -> None:
    def b(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return pen.box(ox + x0 * scale, oy + y0 * scale, ox + x1 * scale, oy + y1 * scale)

    mask, draw = pen.mask()
    draw.ellipse(b(2, 13, 14, 25), fill=255)
    draw.ellipse(b(8, 6, 22, 20), fill=255)
    draw.ellipse(b(17, 11, 29, 23), fill=255)
    draw.rounded_rectangle(b(6, 16, 26, 25), radius=pen.s(3 * scale), fill=255)
    pen.fill(mask, top, bottom, alpha=alpha)


def _passing_cloud(pen: Pen, t: float | None) -> None:
    """A small cloud that drifts in from the left and fades out behind the big one."""
    if t is None:
        return
    progress = t % 1.0
    fade_in, fade_out = min(1.0, progress / 0.15), min(1.0, (1 - progress) / 0.35)
    _cloud(
        pen,
        ox=-14 + 26 * progress,
        oy=1,
        scale=0.5,
        top=(235, 240, 250),
        bottom=(150, 165, 195),
        alpha=round(255 * min(fade_in, fade_out)),
    )


def _drop(pen: Pen, x: float, y: float, size: float = 1.0, alpha: int = 255) -> None:
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
    pen.fill(mask, (170, 230, 255), (20, 110, 255), outline_width=0.6, alpha=alpha)


def _flake(pen: Pen, x: float, y: float, r: float = 2.6, alpha: int = 255) -> None:
    mask, draw = pen.mask()
    width = max(1, int(pen.s(0.9)))
    for i in range(3):
        angle = math.radians(i * 60 + 90)
        dx, dy = math.cos(angle) * r, math.sin(angle) * r
        draw.line(
            (pen.s(x - dx), pen.s(y - dy), pen.s(x + dx), pen.s(y + dy)), fill=255, width=width
        )
    draw.ellipse(pen.box(x - 0.9, y - 0.9, x + 0.9, y + 0.9), fill=255)
    pen.fill(mask, (255, 255, 255), (180, 225, 255), outline_width=0.6, alpha=alpha)


def _hailstones(pen: Pen, stones: list[tuple[float, float]], alpha: int = 255) -> None:
    mask, draw = pen.mask()
    for x, y in stones:
        draw.ellipse(pen.box(x - 1.8, y - 1.8, x + 1.8, y + 1.8), fill=255)
    pen.fill(mask, (255, 255, 255), (150, 200, 240), outline_width=0.6, alpha=alpha)


def _bolt(pen: Pen, ox: float = 0, oy: float = 0, alpha: int = 255) -> None:
    mask, draw = pen.mask()
    points = [(17, 15), (10.5, 23), (14.5, 23), (12, 31), (21, 20.5), (16.5, 20.5), (19.5, 15)]
    draw.polygon([(pen.s(ox + x), pen.s(oy + y)) for x, y in points], fill=255)
    pen.fill(
        mask, (255, 255, 160), (255, 170, 0), outline=(120, 50, 0), outline_width=0.8, alpha=alpha
    )


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


def _twinkle(
    t: float | None, stars: list[tuple[float, float, float]]
) -> list[tuple[float, float, float]]:
    """Each star grows and shrinks a little, out of step with the others."""
    return [(x, y, r * (1 + 0.25 * _wave(t, i * 0.37))) for i, (x, y, r) in enumerate(stars)]


def _under_cloud(t: float | None, cloud: Callable[[], None], falling: Callable[[], None]) -> None:
    """Rain and snow fall out from behind the cloud; the still icon has them in front."""
    if t is None:
        cloud()
        falling()
    else:
        falling()
        cloud()


_STORM_CLOUD = ((150, 155, 185), (80, 80, 115))


def _storm_cloud(pen: Pen, t: float | None) -> None:
    """The dark thunder cloud, lit up during a strike."""
    level = 0.0 if t is None else flash("lightning", t)
    top, bottom = _STORM_CLOUD
    _cloud(
        pen,
        ox=1,
        oy=-5,
        scale=0.95,
        top=mix(top, (255, 255, 255), 0.6 * level),
        bottom=mix(bottom, (200, 200, 240), 0.5 * level),
    )


def _storm_bolt(pen: Pen, t: float | None) -> None:
    """The bolt glows faintly, then blazes during a strike."""
    alpha = 255 if t is None else round(110 + 145 * flash("lightning", t))
    _bolt(pen, ox=0, oy=-1, alpha=alpha)


# ------------------------------------------------------------------- icons


def sunny(pen: Pen, t: float | None) -> None:
    # The rays turn on every other frame. The encoder merges each identical pair, which
    # halves the file, and at this speed the turn still looks smooth.
    step = None if t is None else math.floor(t * 16) / 16
    _sun(pen, spin=step or 0.0, glow=1 + 0.15 * _wave(step))


def clear_night(pen: Pen, t: float | None) -> None:
    _stars(pen, _twinkle(t, [(5, 7, 2.2), (26, 25, 1.8), (27, 6, 1.4), (7, 26, 1.2)]))
    crescent = _moon(pen, (7, 6, 25, 24), (13, 2, 30, 19))
    craters, draw = pen.mask()
    draw.ellipse(pen.box(10.5, 15, 13, 17.5), fill=255)
    draw.ellipse(pen.box(14, 19.5, 15.8, 21.3), fill=255)
    pen.fill(ImageChops.multiply(craters, crescent), (215, 180, 110), (200, 160, 90), outline=None)


def partly_cloudy(pen: Pen, t: float | None) -> None:
    _sun(pen, cx=11, cy=11, r=6)
    _passing_cloud(pen, t)
    _cloud(pen, ox=5, oy=6, scale=0.85)


def partly_cloudy_night(pen: Pen, t: float | None) -> None:
    _moon(pen, (3, 3, 17, 17), (8, 0, 21, 13))
    _stars(pen, _twinkle(t, [(24, 5, 1.6)]))
    _passing_cloud(pen, t)
    _cloud(pen, ox=5, oy=6, scale=0.85)


def cloudy(pen: Pen, t: float | None) -> None:
    drift = 1.2 * _wave(t)
    _cloud(pen, ox=-3 - drift, oy=-3, scale=0.8, top=(170, 180, 200), bottom=(105, 115, 140))
    _cloud(pen, ox=3 + drift, oy=4, scale=0.9)


def fog(pen: Pen, t: float | None) -> None:
    _cloud(pen, ox=2, oy=-4, scale=0.85, top=(200, 210, 225), bottom=(140, 150, 175))
    mask, draw = pen.mask()
    for i, (y, x0, x1) in enumerate(((19.5, 3, 25), (23.5, 7, 29), (27.5, 2, 22))):
        shift = 1.8 * _wave(t, i / 3)
        draw.rounded_rectangle(
            pen.box(x0 + shift, y, x1 + shift, y + 2.2), radius=pen.s(1.1), fill=255
        )
    pen.fill(mask, (235, 240, 250), (180, 190, 210), outline_width=0.6)


def rainy(pen: Pen, t: float | None) -> None:
    def falling() -> None:
        for i, (x, still) in enumerate(((9, 23), (16, 26), (23, 23))):
            y, alpha = _fall(t, still, i / 3, 2, 16, 30)
            _drop(pen, x, y, alpha=alpha)

    _under_cloud(t, lambda: _cloud(pen, ox=1, oy=-4, scale=0.95), falling)


def pouring(pen: Pen, t: float | None) -> None:
    def falling() -> None:
        drops = ((6, 22), (12, 26), (18, 22), (24, 26), (15, 18.5))
        for i, (x, still) in enumerate(drops):
            y, alpha = _fall(t, still, (i * 2 % 5) / 5, 3, 15, 30)
            _drop(pen, x, y, 0.85, alpha=alpha)

    _under_cloud(
        t,
        lambda: _cloud(pen, ox=1, oy=-5, scale=0.95, top=(185, 195, 215), bottom=(105, 115, 145)),
        falling,
    )


def snowy(pen: Pen, t: float | None) -> None:
    def falling() -> None:
        for i, (x, still) in enumerate(((8, 24), (16, 28), (24, 24))):
            y, alpha = _fall(t, still, i / 3, 1, 17, 31)
            _flake(pen, x + 1.2 * _wave(t, i / 3), y, alpha=alpha)

    _under_cloud(t, lambda: _cloud(pen, ox=1, oy=-5, scale=0.95), falling)


def snowy_rainy(pen: Pen, t: float | None) -> None:
    def falling() -> None:
        y, alpha = _fall(t, 24, 0, 1, 17, 31)
        _flake(pen, 9 + _wave(t), y, alpha=alpha)
        y, alpha = _fall(t, 25, 0.5, 2, 16, 30)
        _drop(pen, 16, y, alpha=alpha)
        y, alpha = _fall(t, 25, 0.5, 1, 17, 31)
        _flake(pen, 23 + _wave(t, 0.5), y, alpha=alpha)

    _under_cloud(t, lambda: _cloud(pen, ox=1, oy=-5, scale=0.95), falling)


def hail(pen: Pen, t: float | None) -> None:
    stones = ((8, 23), (15, 27), (22, 23), (19, 29.5))

    def falling() -> None:
        if t is None:
            _hailstones(pen, list(stones))
            return
        for i, (x, still) in enumerate(stones):
            y, alpha = _fall(t, still, i / 4, 3, 17, 31)
            _hailstones(pen, [(x, y)], alpha=alpha)

    _under_cloud(
        t,
        lambda: _cloud(pen, ox=1, oy=-5, scale=0.95, top=(185, 195, 215), bottom=(105, 115, 145)),
        falling,
    )


def lightning(pen: Pen, t: float | None) -> None:
    _storm_cloud(pen, t)
    _storm_bolt(pen, t)


def lightning_rainy(pen: Pen, t: float | None) -> None:
    def falling() -> None:
        for i, (x, still) in enumerate(((6.5, 23), (25, 24))):
            y, alpha = _fall(t, still, i / 2, 2, 16, 30)
            _drop(pen, x, y, 0.85, alpha=alpha)

    _under_cloud(t, lambda: _storm_cloud(pen, t), falling)
    _storm_bolt(pen, t)


def windy(pen: Pen, t: float | None) -> None:
    mask, draw = pen.mask()
    width = int(pen.s(2.2))
    # Each gust slides back and forth on its own beat.
    a, b, c = (1.5 * _wave(t, phase) for phase in (0, 0.33, 0.66))
    draw.line((pen.s(2 + a), pen.s(11), pen.s(20 + a), pen.s(11)), fill=255, width=width)
    draw.arc(pen.box(16 + a, 4, 26 + a, 13), 160, 90, fill=255, width=width)
    draw.line((pen.s(2 + b), pen.s(17), pen.s(27 + b), pen.s(17)), fill=255, width=width)
    draw.line((pen.s(5 + c), pen.s(23), pen.s(17 + c), pen.s(23)), fill=255, width=width)
    draw.arc(pen.box(13 + c, 21, 23 + c, 30), 270, 200, fill=255, width=width)
    pen.fill(mask, (220, 255, 255), (90, 210, 240), outline_width=0.7)


def exceptional(pen: Pen, t: float | None) -> None:
    glow = 0.0 if t is None else 0.5 + 0.5 * _wave(t, 0.25)
    mask, draw = pen.mask()
    draw.polygon([(pen.s(16), pen.s(3)), (pen.s(30), pen.s(28)), (pen.s(2), pen.s(28))], fill=255)
    pen.fill(
        mask.filter(ImageFilter.MaxFilter(5)),
        mix((255, 200, 40), (255, 255, 200), 0.5 * glow),
        mix((255, 60, 30), (255, 140, 60), 0.5 * glow),
    )
    mark, draw = pen.mask()
    draw.rounded_rectangle(pen.box(14.6, 11, 17.4, 21), radius=pen.s(1.2), fill=255)
    draw.ellipse(pen.box(14.5, 22.5, 17.5, 25.5), fill=255)
    pen.fill(mark, (60, 10, 0), (60, 10, 0), outline=None)


# Icons with slower motion loop over this many standard loops.
SLOW: dict[str, int] = {"partlycloudy": 2, "partlycloudy-night": 2}

ICONS: dict[str, Callable[[Pen, float | None], None]] = {
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


def render_icon(condition: str | None, size: int = 32, t: float | None = None) -> Image.Image:
    """An RGBA icon for a Home Assistant weather condition: still, or at loop position t."""
    pen = Pen(size)
    ICONS.get(condition or "", cloudy)(pen, t)
    return pen.result()
