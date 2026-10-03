"""Brightness controls for Tuneshine."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TuneshineConfigEntry
from .api import TuneshineError
from .entity import TuneshineEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TuneshineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            BrightnessNumber(coordinator, "active_brightness", "active"),
            BrightnessNumber(coordinator, "idle_brightness", "idle"),
        ]
    )


class BrightnessNumber(TuneshineEntity, NumberEntity):
    """Active (artwork) or idle brightness."""

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._field = field

    @property
    def native_value(self) -> float | None:
        brightness = (self.coordinator.data or {}).get("config", {}).get("brightness", {})
        return brightness.get(self._field)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_brightness(**{self._field: int(value)})
        except TuneshineError as err:
            raise HomeAssistantError(f"Could not set brightness: {err}") from err
        await self.coordinator.async_request_refresh()
