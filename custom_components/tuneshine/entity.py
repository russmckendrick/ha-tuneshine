"""Base entity for Tuneshine."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import TuneshineCoordinator


class TuneshineEntity(CoordinatorEntity[TuneshineCoordinator]):
    """Common device info and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TuneshineCoordinator, key: str) -> None:
        super().__init__(coordinator)
        mac = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        state = coordinator.data or {}
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer=MANUFACTURER,
            model="Tuneshine",
            name=state.get("name") or coordinator.config_entry.title,
            sw_version=state.get("firmwareVersion"),
            configuration_url=coordinator.client.base_url,
        )
