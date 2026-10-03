"""When the idle screen should be running."""

from __future__ import annotations

from datetime import datetime, time, timedelta

# States of a condition entity that mean "run the idle screen".
ACTIVE_STATES = frozenset({"on", "home", "true", "open"})


def parse_time(value: str | None) -> time | None:
    """Parse an 'HH:MM[:SS]' option, ignoring blanks."""
    if not value:
        return None
    return time.fromisoformat(value)


def in_window(now: datetime, start: time | None, end: time | None) -> tuple[bool, datetime | None]:
    """Whether now is inside the daily window, and when that next changes.

    With no window (or start == end) the screen is always allowed. Windows may
    wrap past midnight, e.g. 22:00 to 07:00.
    """
    if start is None or end is None or start == end:
        return True, None

    current = now.time()
    if start < end:
        active = start <= current < end
    else:
        active = current >= start or current < end

    boundaries = [
        datetime.combine(now.date() + timedelta(days=offset), moment, now.tzinfo)
        for offset in (0, 1)
        for moment in (start, end)
    ]
    next_change = min(boundary for boundary in boundaries if boundary > now)
    return active, next_change
