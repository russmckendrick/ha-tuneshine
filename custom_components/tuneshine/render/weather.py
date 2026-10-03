"""Weather page: a shaded icon, the temperature, condition and high/low."""

from __future__ import annotations

from PIL import Image, ImageDraw

from .animation import GAP, LOOP, Animation, marquee
from .font import FONT_5X7, Color
from .icons import ICONS, SLOW, flash, render_icon
from .style import (
    SIZE,
    Theme,
    background,
    centered_text,
    scrolling_text,
    temperature_color,
    text,
)

LABELS = {
    "clear-night": "Clear",
    "cloudy": "Cloudy",
    "exceptional": "Warning",
    "fog": "Foggy",
    "hail": "Hail",
    "lightning": "Thunder",
    "lightning-rainy": "Storms",
    "partlycloudy": "Partly",
    "partlycloudy-night": "Partly",
    "pouring": "Pouring",
    "rainy": "Rainy",
    "snowy": "Snowy",
    "snowy-rainy": "Sleet",
    "sunny": "Sunny",
    "windy": "Windy",
    "windy-variant": "Windy",
}

_SKY = Theme(
    (0, 34, 84), (0, 70, 110), (255, 255, 255), (200, 240, 255), (255, 210, 60), (150, 200, 230)
)
_NIGHT = Theme(
    (2, 4, 28), (16, 10, 52), (240, 240, 255), (190, 190, 255), (200, 180, 255), (130, 130, 190)
)
_GREY = Theme(
    (16, 24, 40), (36, 48, 70), (255, 255, 255), (200, 215, 235), (170, 210, 255), (150, 165, 190)
)
_RAIN = Theme(
    (4, 18, 46), (10, 36, 80), (255, 255, 255), (170, 220, 255), (90, 180, 255), (130, 170, 210)
)
_SNOW = Theme(
    (14, 30, 56), (40, 64, 96), (255, 255, 255), (210, 235, 255), (200, 235, 255), (170, 190, 215)
)
_STORM = Theme(
    (20, 6, 40), (44, 14, 70), (255, 255, 255), (230, 210, 255), (255, 220, 60), (170, 150, 200)
)
_ALERT = Theme(
    (50, 4, 4), (80, 20, 0), (255, 255, 255), (255, 210, 180), (255, 160, 40), (220, 160, 140)
)

THEMES: dict[str, Theme] = {
    "clear-night": _NIGHT,
    "partlycloudy-night": _NIGHT,
    "sunny": _SKY,
    "partlycloudy": _SKY,
    "windy": _SKY,
    "windy-variant": _GREY,
    "cloudy": _GREY,
    "fog": _GREY,
    "rainy": _RAIN,
    "pouring": _RAIN,
    "snowy": _SNOW,
    "snowy-rainy": _SNOW,
    "hail": _SNOW,
    "lightning": _STORM,
    "lightning-rainy": _STORM,
    "exceptional": _ALERT,
}

# Fuller names for when the label can scroll.
SCROLLING_LABELS = {
    "partlycloudy": "Partly cloudy",
    "partlycloudy-night": "Partly cloudy",
}

WARM: Color = (255, 120, 70)
# The condition label scrolls when it's wider than this.
_LABEL_WIDTH = SIZE - 4
_LIGHTNING: Color = (255, 255, 235)
COOL: Color = (80, 180, 255)

__all__ = ["ICONS", "LABELS", "render_weather"]


def _temp(value: float | None) -> str:
    return "--°" if value is None else f"{round(value)}°"


def _arrow(draw: ImageDraw.ImageDraw, x: int, y: int, up: bool, color: Color) -> None:
    if up:
        draw.polygon([(x + 2, y), (x + 4, y + 3), (x, y + 3)], fill=color)
    else:
        draw.polygon([(x, y + 1), (x + 4, y + 1), (x + 2, y + 4)], fill=color)


def render_weather(
    condition: str | None,
    temperature: float | None,
    *,
    high: float | None = None,
    low: float | None = None,
    label: str | None = None,
    celsius: bool = True,
    animate: bool = True,
) -> Image.Image | Animation:
    """Render the current conditions.

    Animated, it's a loop: a moving icon and, if needed, a scrolling label.
    Otherwise it's one frame with the still icon.
    """
    theme = THEMES.get(condition or "", _GREY)
    fallback = (condition or "Unknown").replace("-", " ").title()
    if not animate:
        name = label or LABELS.get(condition or "", fallback)
        image, draw = background(theme)
        icon = render_icon(condition, 32)
        image.paste(icon, (0, 1), icon)
        _temperature(image, temperature, celsius)
        centered_text(image, FONT_5X7, 37, name, theme.text_top, theme.text_bottom)
        _high_low(image, draw, high, low)
        return image

    name = label or SCROLLING_LABELS.get(condition or "") or LABELS.get(condition or "", fallback)
    period = LOOP * SLOW.get(condition or "", 1)
    icons = [render_icon(condition, 32, i / period) for i in range(period)]
    name_width = FONT_5X7.text_width(name, bold=True)
    offsets = marquee(name_width, _LABEL_WIDTH, period)

    frames = []
    for index, offset in enumerate(offsets):
        image, draw = background(theme)
        icon = icons[index % period]
        image.paste(icon, (0, 1), icon)
        _temperature(image, temperature, celsius)
        if name_width <= _LABEL_WIDTH:
            centered_text(image, FONT_5X7, 37, name, theme.text_top, theme.text_bottom)
        else:
            scrolling_text(
                image,
                FONT_5X7,
                (2, 37),
                _LABEL_WIDTH,
                name,
                offset,
                GAP,
                theme.text_top,
                theme.text_bottom,
            )
        _high_low(image, draw, high, low)
        if level := flash(condition, (index % period) / period):
            image = Image.blend(image, Image.new("RGB", image.size, _LIGHTNING), 0.35 * level)
        frames.append(image)
    return Animation(frames)


def _temperature(image: Image.Image, temperature: float | None, celsius: bool) -> None:
    """Big temperature, coloured by how warm it is."""
    value = _temp(temperature)
    celsius_value = temperature if celsius or temperature is None else (temperature - 32) * 5 / 9
    top, bottom = temperature_color(celsius_value)
    for scale in ((2, 3), (2, 2), (1, 2)):
        width = FONT_5X7.text_width(value, scale[0], bold=True)
        if width <= 32:
            break
    height = FONT_5X7.height * scale[1]
    text(
        image,
        FONT_5X7,
        (32 + (32 - width) // 2, 3 + (24 - height) // 2),
        value,
        top,
        bottom,
        scale=scale,
    )


def _high_low(
    image: Image.Image, draw: ImageDraw.ImageDraw, high: float | None, low: float | None
) -> None:
    if high is None and low is None:
        return
    parts: list[tuple[bool, str]] = []
    if high is not None:
        parts.append((True, _temp(high)))
    if low is not None:
        parts.append((False, _temp(low)))
    widths = [6 + FONT_5X7.text_width(t, bold=True) for _, t in parts]
    gap = 5
    x = (SIZE - sum(widths) - gap * (len(parts) - 1)) // 2
    for (up, value_text), part_width in zip(parts, widths, strict=True):
        color = WARM if up else COOL
        _arrow(draw, x, 52, up, color)
        text(image, FONT_5X7, (x + 6, 50), value_text, color, shadow=True)
        x += part_width + gap
