"""Animated pages: a short loop of 64x64 frames that the device plays on repeat."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

# ~14 frames a second: smooth enough for a 1 px/frame scroll on the matrix.
FRAME_MS = 70
# Frames in one weather icon loop (~2.2 s) and one live-dot pulse (~1.1 s).
LOOP = 32
PULSE = 16
# A scrolling label rests on its start this long (~1.7 s) before moving.
HOLD = 24
# Blank pixels between the end of a scrolling label and its next pass.
GAP = 16


@dataclass
class Animation:
    """Frames shown for duration ms each, looping forever."""

    frames: list[Image.Image]
    duration: int = FRAME_MS


def marquee(width: int, window: int, period: int) -> list[int]:
    """Per-frame scroll offsets for a label width px wide in a window px wide.

    A label that fits stays still for one period. One that doesn't rests on its
    start, then scrolls one full lap so the next pass lines up with frame 0. The
    rest is stretched so the loop is a whole number of periods, which keeps any
    other motion in the frame (a pulse, an icon) seamless too.
    """
    if width <= window:
        return [0] * period
    lap = width + GAP
    hold = HOLD + (-(HOLD + lap)) % period
    return [0] * hold + list(range(lap))
