"""Schedule window tests."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from custom_components.tuneshine.schedule import in_window, parse_time


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, tzinfo=UTC)


def test_no_window_is_always_on() -> None:
    assert in_window(at(3), None, None) == (True, None)
    assert in_window(at(3), time(8), time(8)) == (True, None)


@pytest.mark.parametrize(
    ("now", "active", "next_change"),
    [
        (at(6, 59), False, at(7)),
        (at(7), True, at(23)),
        (at(12), True, at(23)),
        (at(23), False, datetime(2026, 10, 4, 7, tzinfo=UTC)),
    ],
)
def test_daytime_window(now: datetime, active: bool, next_change: datetime) -> None:
    assert in_window(now, time(7), time(23)) == (active, next_change)


@pytest.mark.parametrize(
    ("now", "active", "next_change"),
    [
        (at(21), False, at(22)),
        (at(22, 30), True, datetime(2026, 10, 4, 6, tzinfo=UTC)),
        (at(5), True, at(6)),
        (at(6), False, at(22)),
    ],
)
def test_overnight_window(now: datetime, active: bool, next_change: datetime) -> None:
    assert in_window(now, time(22), time(6)) == (active, next_change)


def test_parse_time() -> None:
    assert parse_time("07:30:00") == time(7, 30)
    assert parse_time("") is None
    assert parse_time(None) is None
