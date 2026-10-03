"""Client for the Tuneshine local HTTP API."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import REQUEST_TIMEOUT, UPLOAD_TIMEOUT


class TuneshineError(Exception):
    """Base error talking to a Tuneshine."""


class TuneshineConnectionError(TuneshineError):
    """The device could not be reached."""


class TuneshineClient:
    """Minimal async client for the Tuneshine device API."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self.host = host

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    async def _request(
        self, method: str, path: str, *, timeout: float = REQUEST_TIMEOUT, **kwargs: Any
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                timeout=aiohttp.ClientTimeout(total=timeout),
                **kwargs,
            ) as response:
                body = await response.read()
                if response.status >= 400:
                    raise TuneshineError(
                        f"{method} {path} returned {response.status}: {body[:200]!r}"
                    )
        except (TimeoutError, aiohttp.ClientError) as err:
            raise TuneshineConnectionError(f"{method} {path} failed: {err}") from err
        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError as err:
            raise TuneshineError(f"{method} {path} returned invalid JSON") from err

    async def get_state(self) -> dict[str, Any]:
        """Return the device state."""
        return await self._request("GET", "/state")

    async def post_image(self, image: bytes, metadata: dict[str, Any]) -> None:
        """Upload a 64x64 WebP with metadata."""
        form = aiohttp.FormData()
        form.add_field("image", image, filename="image.webp", content_type="image/webp")
        form.add_field("metadata", json.dumps(metadata))
        await self._request("POST", "/image", data=form, timeout=UPLOAD_TIMEOUT)

    async def delete_image(self, *, preserve_image: bool | None = None) -> None:
        """Remove the local image and fall back to whatever the device shows next."""
        body = {} if preserve_image is None else {"preserveImage": preserve_image}
        await self._request("DELETE", "/image", json=body)

    async def set_brightness(self, *, active: int | None = None, idle: int | None = None) -> None:
        """Set active and/or idle brightness (1-100)."""
        body = {
            key: value for key, value in (("active", active), ("idle", idle)) if value is not None
        }
        await self._request("POST", "/brightness", json=body)
