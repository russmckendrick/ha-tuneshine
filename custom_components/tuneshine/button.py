"""Button to skip to the next idle page."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TuneshineConfigEntry
from .entity import TuneshineEntity
from .idle import IdleScreenManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TuneshineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities([NextPageButton(data.coordinator, "next_page", data.idle)])


class NextPageButton(TuneshineEntity, ButtonEntity):
    """Advance the idle rotation."""

    def __init__(self, coordinator, key: str, idle: IdleScreenManager) -> None:
        super().__init__(coordinator, key)
        self._idle = idle

    async def async_press(self) -> None:
        self._idle.async_next_page()
