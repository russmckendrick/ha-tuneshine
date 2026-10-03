"""Sensors for Tuneshine."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TuneshineConfigEntry
from .const import PAGE_TYPES
from .entity import TuneshineEntity
from .idle import IdleScreenManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TuneshineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            NowPlayingSensor(coordinator, "now_playing"),
            ImageSourceSensor(coordinator, "image_source"),
            IdlePageSensor(coordinator, "idle_page", entry.runtime_data.idle),
        ]
    )


class NowPlayingSensor(TuneshineEntity, SensorEntity):
    """Track currently on the screen, from the Tuneshine cloud."""

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.is_playing:
            return None
        return (self.coordinator.remote or {}).get("trackName")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        remote = self.coordinator.remote if self.coordinator.is_playing else None
        remote = remote or {}
        return {
            "artist": remote.get("artistName"),
            "album": remote.get("albumName"),
            "service": remote.get("serviceName"),
            "zone": remote.get("zoneName"),
            "content_type": remote.get("contentType"),
        }


class ImageSourceSensor(TuneshineEntity, SensorEntity):
    """Where the current image came from: system, local or remote."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["system", "local", "remote"]  # noqa: RUF012
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("imageSource")


class IdlePageSensor(TuneshineEntity, SensorEntity):
    """The idle-screen page currently in rotation."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key: str, idle: IdleScreenManager) -> None:
        super().__init__(coordinator, key)
        self._idle = idle
        self._attr_options = [page.key for page in idle.pages] or list(PAGE_TYPES)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._idle.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str | None:
        page = self._idle.current_page
        return page.key if page and self._idle.active else None
