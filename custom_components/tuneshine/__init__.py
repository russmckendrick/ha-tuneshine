"""The Tuneshine integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import TuneshineClient
from .const import DOMAIN
from .coordinator import TuneshineCoordinator
from .idle import IdleScreenManager
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class TuneshineData:
    """Runtime data for a config entry."""

    client: TuneshineClient
    coordinator: TuneshineCoordinator
    idle: IdleScreenManager


type TuneshineConfigEntry = ConfigEntry[TuneshineData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TuneshineConfigEntry) -> bool:
    """Set up a Tuneshine from a config entry."""
    client = TuneshineClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    coordinator = TuneshineCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    idle = IdleScreenManager(hass, entry, client, coordinator)
    entry.runtime_data = TuneshineData(client, coordinator, idle)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    idle.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TuneshineConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.idle.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: TuneshineConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
