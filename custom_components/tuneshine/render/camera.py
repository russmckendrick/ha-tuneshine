"""Camera snapshot page."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .font import FONT_3X5, Color
from .style import SIZE, fit_text, scale_color


def render_camera(
    data: bytes,
    *,
    label: str | None = None,
    accent: Color = (255, 60, 60),
) -> Image.Image:
    """Centre-crop a snapshot to 64x64, punched up for LEDs, with a name tag."""
    with Image.open(io.BytesIO(data)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        image = ImageOps.fit(source, (SIZE, SIZE), Image.Resampling.LANCZOS)

    image = ImageEnhance.Contrast(image).enhance(1.2)
    image = ImageEnhance.Color(image).enhance(1.35)
    image = ImageEnhance.Sharpness(image).enhance(1.3)

    if label:
        # Darken the bottom rows so the tag reads on any scene.
        strip = image.crop((0, SIZE - 9, SIZE, SIZE))
        image.paste(Image.blend(strip, Image.new("RGB", strip.size), 0.65), (0, SIZE - 9))
        draw = ImageDraw.Draw(image)
        text = fit_text(FONT_3X5, label.upper(), SIZE - 12)
        # A red "live" dot, then the camera name.
        draw.ellipse((2, SIZE - 7, 5, SIZE - 4), fill=accent)
        draw.point((3, SIZE - 6), fill=scale_color(accent, 1.6))
        FONT_3X5.draw(draw, (8, SIZE - 7), text, (255, 255, 255))

    return image
