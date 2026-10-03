"""Render 64x64 frames for the Tuneshine.

Everything in this package is plain Pillow with no Home Assistant imports, so
frames can be previewed and tested without a running Home Assistant.
"""

from __future__ import annotations

import io

from PIL import Image

from .animation import Animation
from .camera import render_camera
from .clock import render_clock
from .font import FONT_3X5, FONT_5X7, Color, PixelFont
from .style import PAGE_THEMES, Theme
from .text import render_text
from .weather import render_weather

SIZE = 64
MAX_BYTES = 768 * 1024

__all__ = [
    "FONT_3X5",
    "FONT_5X7",
    "MAX_BYTES",
    "PAGE_THEMES",
    "SIZE",
    "Animation",
    "Color",
    "PixelFont",
    "Theme",
    "render_camera",
    "render_clock",
    "render_text",
    "render_weather",
    "to_webp",
]


def to_webp(page: Image.Image | Animation) -> bytes:
    """Encode a frame, or a looping animation, as the 64x64 WebP the device expects."""
    frames = page.frames if isinstance(page, Animation) else [page]
    frames = [
        (f if f.size == (SIZE, SIZE) else f.resize((SIZE, SIZE), Image.Resampling.LANCZOS)).convert(
            "RGB"
        )
        for f in frames
    ]
    buffer = io.BytesIO()
    if len(frames) == 1:
        frames[0].save(buffer, format="WEBP", lossless=True, quality=100)
    else:
        frames[0].save(
            buffer,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=page.duration,
            loop=0,
            lossless=True,
            quality=100,
        )
    return buffer.getvalue()
