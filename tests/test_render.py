"""Renderer tests: every page is a valid 64x64 frame."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from custom_components.tuneshine.render import (
    MAX_BYTES,
    render_camera,
    render_clock,
    render_text,
    render_weather,
    to_webp,
)
from custom_components.tuneshine.render.font import FONT_5X7
from custom_components.tuneshine.render.icons import ICONS
from custom_components.tuneshine.render.text import _layout, wrap


def _check(image: Image.Image) -> None:
    assert image.size == (64, 64)
    data = to_webp(image)
    assert len(data) < MAX_BYTES
    with Image.open(io.BytesIO(data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (64, 64)


@pytest.mark.parametrize("use_24h", [True, False])
@pytest.mark.parametrize("show_date", [True, False])
@pytest.mark.parametrize("hour", [0, 9, 12, 23])
def test_clock(use_24h: bool, show_date: bool, hour: int) -> None:
    _check(
        render_clock(
            datetime(2026, 10, 3, hour, 7, tzinfo=UTC), use_24h=use_24h, show_date=show_date
        )
    )


@pytest.mark.parametrize("condition", [*ICONS, "something-new", None])
def test_weather(condition: str | None) -> None:
    _check(render_weather(condition, -12.4, high=1, low=-15))
    _check(render_weather(condition, None))


def test_camera() -> None:
    source = Image.new("RGB", (1920, 1080), (10, 200, 30))
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG")
    _check(render_camera(buffer.getvalue(), label="A very long camera name indeed"))
    _check(render_camera(buffer.getvalue()))


@pytest.mark.parametrize(
    "text",
    ["", "21.5°", "Office|21.5°C", "Line one\nline two\nline three", "x" * 500, "word " * 80],
)
def test_text(text: str) -> None:
    _check(render_text(text))


def test_text_layout_prefers_big() -> None:
    layout = _layout("21.5°")
    assert layout.heading is None
    assert len(layout.lines) == 1
    assert layout.lines[0].scale[0] == 2


def test_text_layout_heading() -> None:
    layout = _layout("Solar|3.2 kW")
    assert layout.heading == "Solar"
    assert [line.text for line in layout.lines] == ["3.2 kW"]


def test_text_layout_long_heading_stays_in_body() -> None:
    layout = _layout("Washing machine|Finished 10 minutes ago")
    assert layout.heading is None
    assert layout.lines[0].accent


def test_bold_keeps_single_pixel_gaps() -> None:
    mask = FONT_5X7.mask("m", bold=True)
    # Row 4 of 'm' is "#.#.#": the gaps must survive bolding.
    row = [mask.getpixel((x, 4)) for x in range(mask.width)]
    assert row[1] == 0
    assert row[3] == 0


@pytest.mark.parametrize("theme", [0, 1, 7])
def test_text_themes(theme: int) -> None:
    _check(render_text("Office|21.5°", theme=theme))


def test_wrap_breaks_long_words() -> None:
    lines = wrap(FONT_5X7, "supercalifragilisticexpialidocious")
    assert len(lines) > 1
    assert all(FONT_5X7.text_width(line) <= 64 for line in lines)
