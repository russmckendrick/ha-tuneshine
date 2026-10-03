"""Album artwork as an image entity."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TuneshineConfigEntry
from .coordinator import TuneshineCoordinator
from .entity import TuneshineEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TuneshineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ArtworkImage(hass, entry.runtime_data.coordinator)])


class ArtworkImage(TuneshineEntity, ImageEntity):
    """Now-playing artwork from the Tuneshine cloud."""

    def __init__(self, hass: HomeAssistant, coordinator: TuneshineCoordinator) -> None:
        TuneshineEntity.__init__(self, coordinator, "artwork")
        ImageEntity.__init__(self, hass)
        self._attr_image_url = self._current_url()
        self._attr_image_last_updated = dt_util.utcnow()

    def _current_url(self) -> str | None:
        if not self.coordinator.is_playing:
            return None
        return (self.coordinator.remote or {}).get("imageUrl")

    @callback
    def _handle_coordinator_update(self) -> None:
        url = self._current_url()
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
