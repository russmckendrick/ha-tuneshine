"""Polls the Tuneshine for its current state."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TuneshineClient, TuneshineError
from .const import DOMAIN, ITEM_PREFIX, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# The device is a small microcontroller and drops the odd request, so only
# mark entities unavailable after several polls in a row fail.
_FAILURES_BEFORE_UNAVAILABLE = 3


class TuneshineCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch /state every few seconds."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: TuneshineClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )
        self.client = client
        self._failures = 0

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.client.get_state()
        except TuneshineError as err:
            self._failures += 1
            if self.data is not None and self._failures < _FAILURES_BEFORE_UNAVAILABLE:
                return self.data
            raise UpdateFailed(f"Error talking to Tuneshine: {err}") from err
        self._failures = 0
        return state

    @property
    def remote(self) -> dict[str, Any] | None:
        """Metadata pushed by the Tuneshine cloud, if any."""
        return (self.data or {}).get("remoteMetadata")

    @property
    def local(self) -> dict[str, Any] | None:
        """Metadata for the image set over the local API, if any."""
        return (self.data or {}).get("localMetadata")

    @property
    def is_playing(self) -> bool:
        """True while the device is showing (or holding) now-playing artwork."""
        remote = self.remote
        return bool(remote) and remote.get("idle") is False

    @property
    def showing_ours(self) -> bool:
        """True when the screen shows an image this integration pushed."""
        local = self.local or {}
        return (self.data or {}).get("imageSource") == "local" and str(
            local.get("itemId", "")
        ).startswith(ITEM_PREFIX)
