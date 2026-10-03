"""Switch to turn the Home Assistant idle screen on and off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import TuneshineConfigEntry
from .entity import TuneshineEntity
from .idle import IdleScreenManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TuneshineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities([IdleScreenSwitch(data.coordinator, "idle_screen", data.idle)])


class IdleScreenSwitch(TuneshineEntity, SwitchEntity, RestoreEntity):
    """When on, Home Assistant pages replace the stock idle image."""

    def __init__(self, coordinator, key: str, idle: IdleScreenManager) -> None:
        super().__init__(coordinator, key)
        self._idle = idle

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        await self._idle.async_set_enabled(last is None or last.state != STATE_OFF)

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._idle.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._idle.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._idle.async_set_enabled(False)
        self.async_write_ha_state()
