"""Camera snapshot page."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .animation import GAP, PULSE, Animation, marquee
from .font import FONT_3X5, Color
from .style import SIZE, fit_text, scale_color, scrolling_text

# The name runs from just right of the live dot to the edge.
_LABEL_X = 8
_LABEL_WIDTH = SIZE - _LABEL_X - 2


def render_camera(
    data: bytes,
    *,
    label: str | None = None,
    accent: Color = (255, 60, 60),
    animate: bool = True,
) -> Image.Image | Animation:
    """Centre-crop a snapshot to 64x64, punched up for LEDs, with a name tag.

    With a label and animate, it's an animation: the live dot pulses, and a name
    too long for the tag scrolls. Otherwise a long name is cut short.
    """
    with Image.open(io.BytesIO(data)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        image = ImageOps.fit(source, (SIZE, SIZE), Image.Resampling.LANCZOS)

    image = ImageEnhance.Contrast(image).enhance(1.2)
    image = ImageEnhance.Color(image).enhance(1.35)
    image = ImageEnhance.Sharpness(image).enhance(1.3)

    if not label:
        return image

    # Darken the bottom rows so the tag reads on any scene.
    strip = image.crop((0, SIZE - 9, SIZE, SIZE))
    image.paste(Image.blend(strip, Image.new("RGB", strip.size), 0.65), (0, SIZE - 9))

    name = label.upper()
    if not animate:
        _tag(image, fit_text(FONT_3X5, name, SIZE - 12), 0, 1.0, accent)
        return image

    frames = []
    for index, offset in enumerate(marquee(FONT_3X5.text_width(name), _LABEL_WIDTH, PULSE)):
        frame = image.copy()
        # The live dot breathes, brightest at the start of each pulse.
        level = 0.25 + 0.75 * (0.5 + 0.5 * math.cos(2 * math.pi * index / PULSE))
        _tag(frame, name, offset, level, accent)
        frames.append(frame)
    return Animation(frames)


def _tag(image: Image.Image, name: str, offset: int, level: float, accent: Color) -> None:
    """A red "live" dot at the given brightness, then the camera name."""
    scrolling_text(
        image,
        FONT_3X5,
        (_LABEL_X, SIZE - 7),
        _LABEL_WIDTH,
        name,
        offset,
        GAP,
        (255, 255, 255),
        bold=False,
        shadow=False,
    )
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, SIZE - 7, 5, SIZE - 4), fill=scale_color(accent, level))
    if level > 0.6:
        draw.point((3, SIZE - 6), fill=scale_color(accent, 1.6 * level))
