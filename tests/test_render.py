"""Renderer tests: every page is a valid 64x64 frame."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from itertools import pairwise

import pytest
from PIL import Image, ImageChops, ImageStat

from custom_components.tuneshine.render import (
    MAX_BYTES,
    Animation,
    render_camera,
    render_clock,
    render_text,
    render_weather,
    to_webp,
)
from custom_components.tuneshine.render.animation import GAP, HOLD, LOOP, PULSE, marquee
from custom_components.tuneshine.render.font import FONT_5X7
from custom_components.tuneshine.render.icons import ICONS, SLOW
from custom_components.tuneshine.render.text import _layout, wrap


def _check(page: Image.Image | Animation) -> None:
    frames = page.frames if isinstance(page, Animation) else [page]
    assert frames
    assert all(frame.size == (64, 64) for frame in frames)
    data = to_webp(page)
    assert len(data) < MAX_BYTES
    with Image.open(io.BytesIO(data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (64, 64)
        # The encoder merges identical neighbours, so there may be fewer frames.
        assert getattr(decoded, "n_frames", 1) <= len(frames)


def _changed(a: Image.Image, b: Image.Image) -> tuple[int, int, int, int] | None:
    return ImageChops.difference(a, b).getbbox()


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1920, 1080), (10, 200, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


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
    _check(render_camera(_jpeg(), label="A very long camera name indeed"))
    _check(render_camera(_jpeg()))


def test_camera_without_label_is_still() -> None:
    assert isinstance(render_camera(_jpeg()), Image.Image)


def test_camera_short_label_only_pulses_the_dot() -> None:
    page = render_camera(_jpeg(), label="Gate")
    assert isinstance(page, Animation)
    assert len(page.frames) == PULSE
    changed = _changed(page.frames[0], page.frames[PULSE // 2])
    assert changed is not None
    assert changed[2] <= 8  # only the live dot, left of the name


def test_camera_long_label_scrolls() -> None:
    page = render_camera(_jpeg(), label="Back garden doorbell")
    assert isinstance(page, Animation)
    assert len(page.frames) > PULSE
    assert len(page.frames) % PULSE == 0
    # The name holds still at first, then moves.
    assert _changed(page.frames[0], page.frames[1])[0] < 8
    assert _changed(page.frames[0], page.frames[-1])[2] > 8


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


def test_marquee_short_text_stays_still() -> None:
    assert marquee(20, 60, 16) == [0] * 16


@pytest.mark.parametrize("width", [61, 72, 100, 200])
@pytest.mark.parametrize("period", [PULSE, LOOP, LOOP * 2])
def test_marquee_loops_seamlessly(width: int, period: int) -> None:
    offsets = marquee(width, 60, period)
    assert len(offsets) % period == 0
    assert offsets[:HOLD] == [0] * HOLD
    # One pixel a frame, ending one step before the wrapped copy lands on 0.
    assert offsets[-1] == width + GAP - 1
    steps = [b - a for a, b in pairwise(offsets)]
    assert set(steps) <= {0, 1}


def test_clock_colon_blinks() -> None:
    page = render_clock(datetime(2026, 10, 3, 9, 41, tzinfo=UTC))
    assert isinstance(page, Animation)
    assert len(page.frames) == 2
    assert page.duration == 500
    changed = _changed(*page.frames)
    assert changed is not None
    # Only the colon changes: a narrow strip in the middle of the screen.
    assert changed[2] - changed[0] <= 4
    assert 28 <= changed[0] <= 34


@pytest.mark.parametrize("condition", list(ICONS))
def test_weather_icon_loops(condition: str) -> None:
    page = render_weather(condition, 18)
    assert isinstance(page, Animation)
    period = LOOP * SLOW.get(condition, 1)
    assert len(page.frames) % period == 0
    assert any(_changed(page.frames[0], frame) for frame in page.frames[1:])


def test_weather_long_label_scrolls() -> None:
    page = render_weather("sunny", 18, label="Sunny with a chance of meatballs")
    assert len(page.frames) > LOOP
    assert len(page.frames) % LOOP == 0
    label_rows = (0, 37, 64, 46)
    assert page.frames[0].crop(label_rows) != page.frames[-1].crop(label_rows)


def test_weather_lightning_flashes() -> None:
    page = render_weather("lightning", 18)
    brightness = [ImageStat.Stat(frame.convert("L")).mean[0] for frame in page.frames]
    assert max(brightness) > brightness[0] * 1.2


def test_sunny_rays_step_on_alternate_frames() -> None:
    """Pairs of identical frames merge in the WebP, halving the sunny page's size."""
    page = render_weather("sunny", 18)
    assert len(page.frames) == LOOP
    assert all(_changed(page.frames[i], page.frames[i + 1]) is None for i in range(0, LOOP, 2))
    with Image.open(io.BytesIO(to_webp(page))) as decoded:
        assert decoded.n_frames == LOOP // 2


def test_still_pages_are_single_frames() -> None:
    now = datetime(2026, 10, 3, 9, 41, tzinfo=UTC)
    assert isinstance(render_clock(now, animate=False), Image.Image)
    assert isinstance(render_weather("rainy", 18, animate=False), Image.Image)
    assert isinstance(render_camera(_jpeg(), label="Gate", animate=False), Image.Image)
    # The still clock is the animation's colon-on frame.
    assert _changed(render_clock(now, animate=False), render_clock(now).frames[0]) is None


def test_still_weather_keeps_short_label() -> None:
    """Without scrolling, 'Partly cloudy' wouldn't fit, so the still page says 'Partly'."""
    still = render_weather("partlycloudy", 18, animate=False)
    expected = render_weather("partlycloudy", 18, label="Partly", animate=False)
    assert _changed(still, expected) is None
    assert _changed(still, render_weather("partlycloudy", 18, label="Cloudy", animate=False))


def test_still_camera_cuts_long_names() -> None:
    long_name = render_camera(_jpeg(), label="Back garden doorbell", animate=False)
    cut = render_camera(_jpeg(), label="Back garden d", animate=False)
    assert _changed(long_name, cut) is None
