"""Clock page."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from .animation import Animation
from .font import FONT_3X5, FONT_5X7
from .style import SIZE, Theme, background, centered_text, mix, pill, scale_color, text, time_theme

# Digits drawn 2x wide and 3x tall, bold: 11x21 px, a tall retro LED look.
_DIGIT_SCALE = (2, 3)
# The colon blinks: half a second on, half a second off.
_BLINK_MS = 500


def render_clock(
    now: datetime,
    *,
    use_24h: bool = True,
    show_date: bool = True,
    animate: bool = True,
) -> Image.Image | Animation:
    """Render the time, coloured for the time of day, with the date around it.

    Animated, it's two frames, so the colon between hours and minutes blinks once a second.
    """
    if not animate:
        return _clock_frame(now, use_24h, show_date, colon=True)
    return Animation(
        [_clock_frame(now, use_24h, show_date, colon) for colon in (True, False)], _BLINK_MS
    )


def _clock_frame(now: datetime, use_24h: bool, show_date: bool, colon: bool) -> Image.Image:
    theme = time_theme(now.hour)
    image, draw = background(theme)

    hours = f"{now.hour:02d}" if use_24h else str((now.hour % 12) or 12)
    minutes = f"{now.minute:02d}"
    width = FONT_5X7.text_width(f"{hours}:{minutes}", _DIGIT_SCALE[0], bold=True)
    time_y = 14 if show_date else 21

    if use_24h:
        _time(image, (SIZE - width) // 2, time_y, hours, minutes, colon, theme)
    else:
        marker = "AM" if now.hour < 12 else "PM"
        x = (SIZE - width - 5) // 2
        _time(image, x, time_y, hours, minutes, colon, theme)
        for i, letter in enumerate(marker):
            FONT_3X5.draw(draw, (x + width + 2, time_y + 3 + i * 6), letter, theme.accent)

    if show_date:
        pill(
            image,
            FONT_3X5,
            3,
            now.strftime("%A").upper(),
            theme.accent,
            scale_color(theme.bg_top, 0.6),
        )
        date = f"{now.day} {now.strftime('%B').upper()}"
        if FONT_5X7.text_width(date, bold=True) > SIZE - 8:
            date = f"{now.day} {now.strftime('%b').upper()}"
        centered_text(
            image, FONT_5X7, 40, date, mix(theme.muted, (255, 255, 255), 0.4), theme.muted
        )

    _day_progress(draw, now, theme.accent, theme.muted)
    return image


def _time(
    image: Image.Image,
    x: int,
    y: int,
    hours: str,
    minutes: str,
    colon: bool,
    theme: Theme,
) -> None:
    """Draw hours, colon and minutes where they'd land as one string, leaving out the colon."""
    advance = FONT_5X7.spacing * _DIGIT_SCALE[0]
    parts = [(hours, True), (":", colon), (minutes, True)]
    for part, visible in parts:
        if visible:
            text(
                image, FONT_5X7, (x, y), part, theme.text_top, theme.text_bottom, scale=_DIGIT_SCALE
            )
        x += FONT_5X7.text_width(part, _DIGIT_SCALE[0], bold=True) + advance


def _day_progress(draw: ImageDraw.ImageDraw, now: datetime, accent, muted) -> None:
    """A thin bar along the bottom showing how far through the day we are."""
    y = 57
    left, right = 6, SIZE - 7
    fraction = (now.hour * 60 + now.minute) / 1440
    end = left + round((right - left) * fraction)
    draw.line((left, y, right, y), fill=scale_color(muted, 0.35))
    for x in range(left, end + 1):
        draw.point(
            (x, y), fill=mix(scale_color(accent, 0.5), accent, (x - left) / max(end - left, 1))
        )
    draw.rectangle((end - 1, y - 1, end + 1, y + 1), fill=mix(accent, (255, 255, 255), 0.6))
