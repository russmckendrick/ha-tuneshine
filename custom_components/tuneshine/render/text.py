"""Free text page, used for templates and one-off messages.

Lines are split on newlines or '|'. When there is more than one line, the first
is a heading, drawn as a coloured tag across the top. Short values are drawn
big and bold; longer text is word-wrapped and shrunk until it fits.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .font import FONT_3X5, FONT_5X7, Color, PixelFont
from .style import (
    PAGE_THEMES,
    SIZE,
    Theme,
    background,
    centered_text,
    fit_text,
    mix,
    pill,
    scale_color,
)

_GAP = 3
_HEADING_HEIGHT = FONT_3X5.height + 4 + 3


@dataclass(frozen=True)
class _Line:
    text: str
    font: PixelFont
    scale: tuple[int, int]
    bold: bool
    accent: bool = False

    @property
    def height(self) -> int:
        return self.font.height * self.scale[1]

    @property
    def advance(self) -> int:
        if self.scale == (1, 1):
            return self.font.line_height
        return self.height + _GAP

    @property
    def width(self) -> int:
        return self.font.text_width(self.text, self.scale[0], self.bold)


@dataclass(frozen=True)
class _Layout:
    heading: str | None
    lines: list[_Line]


def split_lines(text: str) -> list[str]:
    """Split text into explicit lines, dropping empty ones."""
    lines = text.replace("|", "\n").splitlines()
    return [line.strip() for line in lines if line.strip()]


def wrap(font: PixelFont, text: str, width: int = SIZE, bold: bool = False) -> list[str]:
    """Word-wrap text to a pixel width, hard-breaking words that are too long."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if font.text_width(candidate, bold=bold) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while font.text_width(word, bold=bold) > width:
            cut = max(1, len(fit_text(font, word, width, bold)))
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def _height(lines: list[_Line]) -> int:
    if not lines:
        return 0
    return sum(line.advance for line in lines[:-1]) + lines[-1].height


def _fits(lines: list[_Line], space: int) -> bool:
    return _height(lines) <= space and all(line.width <= SIZE - 2 for line in lines)


def _layout(text: str) -> _Layout:
    explicit = split_lines(text)
    if not explicit:
        return _Layout(None, [])

    multi = len(explicit) > 1
    if multi and FONT_3X5.text_width(explicit[0].upper()) <= SIZE - 8:
        # Short first line: a tag across the top, values below.
        heading, body, accent_first = explicit[0], explicit[1:], False
    else:
        # Long first line: keep it in the body, in the accent colour.
        heading, body, accent_first = None, explicit, multi
    space = SIZE - (_HEADING_HEIGHT if heading else 0) - 2

    if not accent_first:
        for scale in ((2, 3), (2, 2), (1, 2)):
            big = [_Line(t, FONT_5X7, scale, True) for t in body]
            if _fits(big, space):
                return _Layout(heading, big)

    for font, bold in ((FONT_5X7, True), (FONT_5X7, False), (FONT_3X5, False)):
        wrapped = [
            _Line(part, font, (1, 1), bold, accent_first and index == 0)
            for index, line in enumerate(body)
            for part in wrap(font, line, SIZE - 2, bold)
        ]
        if _fits(wrapped, space):
            return _Layout(heading, wrapped)

    max_lines = (space + 1) // FONT_3X5.line_height
    return _Layout(heading, wrapped[:max_lines])


def theme_from_color(color: Color) -> Theme:
    """A theme built around a single colour, for messages with a chosen colour."""
    return Theme(
        scale_color(color, 0.16),
        scale_color(color, 0.32),
        mix(color, (255, 255, 255), 0.75),
        color,
        color,
        mix(color, (255, 255, 255), 0.5),
    )


def render_text(text: str, *, theme: Theme | int | None = None) -> Image.Image:
    """Render text centred on a themed background.

    theme may be a Theme, or an index into the rotating page palettes.
    """
    if not isinstance(theme, Theme):
        theme = PAGE_THEMES[(theme or 0) % len(PAGE_THEMES)]
    image, _draw = background(theme)
    layout = _layout(text)

    top = 0
    if layout.heading:
        pill(
            image, FONT_3X5, 3, layout.heading.upper(), theme.accent, scale_color(theme.bg_top, 0.5)
        )
        top = _HEADING_HEIGHT

    if not layout.lines:
        return image

    space = SIZE - top
    y = top + (space - _height(layout.lines)) // 2
    for line in layout.lines:
        if line.accent:
            colors = (mix(theme.accent, (255, 255, 255), 0.3), theme.accent)
        elif line.scale == (1, 1):
            colors = (theme.text_top, mix(theme.text_top, theme.text_bottom, 0.5))
        else:
            colors = (theme.text_top, theme.text_bottom)
        centered_text(
            image,
            line.font,
            y,
            line.text,
            *colors,
            scale=line.scale,
            bold=line.bold,
            shadow=line.font is FONT_5X7,
        )
        y += line.advance
    return image
