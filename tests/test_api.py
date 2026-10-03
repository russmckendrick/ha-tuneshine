"""API client tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from custom_components.tuneshine.api import TuneshineClient
from custom_components.tuneshine.const import REQUEST_TIMEOUT, UPLOAD_TIMEOUT


class _Response:
    status = 200

    async def read(self) -> bytes:
        return b'{"status": "ok"}'


class _Session:
    """Records the timeout each request was made with."""

    def __init__(self) -> None:
        self.timeouts: dict[tuple[str, str], float | None] = {}

    @asynccontextmanager
    async def request(self, method: str, url: str, *, timeout: Any, **kwargs: Any):
        self.timeouts[(method, url.removeprefix("http://tuneshine"))] = timeout.total
        yield _Response()


async def test_uploads_get_longer_timeout() -> None:
    """Animated WebPs can take the device over 10 s to accept; polling stays quick."""
    session = _Session()
    client = TuneshineClient(session, "tuneshine")  # type: ignore[arg-type]

    await client.post_image(b"webp", {"idle": True})
    await client.get_state()
    await client.delete_image(preserve_image=False)

    assert UPLOAD_TIMEOUT > REQUEST_TIMEOUT
    assert session.timeouts == {
        ("POST", "/image"): UPLOAD_TIMEOUT,
        ("GET", "/state"): REQUEST_TIMEOUT,
        ("DELETE", "/image"): REQUEST_TIMEOUT,
    }
