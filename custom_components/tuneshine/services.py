"""Services for showing things on a Tuneshine from automations."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TuneshineError
from .const import (
    ATTR_CAMERA_ENTITY,
    ATTR_COLOR,
    ATTR_DURATION,
    ATTR_MESSAGE,
    ATTR_PAGE,
    ATTR_URL,
    DEFAULT_ALERT_COLOR,
    DOMAIN,
)
from .render import render_camera, render_text
from .render.text import theme_from_color

if TYPE_CHECKING:
    from .idle import IdleScreenManager

SERVICE_SHOW_TEXT = "show_text"
SERVICE_SHOW_IMAGE = "show_image"
SERVICE_SHOW_PAGE = "show_page"
SERVICE_CLEAR = "clear"

_DEVICES = vol.Optional(ATTR_DEVICE_ID)
_DURATION = vol.Optional(ATTR_DURATION, default=10)

SHOW_TEXT_SCHEMA = vol.Schema(
    {
        _DEVICES: vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_MESSAGE): cv.string,
        _DURATION: vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
        vol.Optional(ATTR_COLOR): vol.All(
            vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
        ),
    }
)
SHOW_IMAGE_SCHEMA = vol.All(
    vol.Schema(
        {
            _DEVICES: vol.All(cv.ensure_list, [cv.string]),
            vol.Exclusive(ATTR_CAMERA_ENTITY, "source"): cv.entity_id,
            vol.Exclusive(ATTR_URL, "source"): cv.url,
            _DURATION: vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
        }
    ),
    cv.has_at_least_one_key(ATTR_CAMERA_ENTITY, ATTR_URL),
)
SHOW_PAGE_SCHEMA = vol.Schema(
    {_DEVICES: vol.All(cv.ensure_list, [cv.string]), vol.Required(ATTR_PAGE): cv.string}
)
CLEAR_SCHEMA = vol.Schema({_DEVICES: vol.All(cv.ensure_list, [cv.string])})


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[IdleScreenManager]:
    """Idle managers for the requested devices, or every loaded Tuneshine."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    device_ids = call.data.get(ATTR_DEVICE_ID)
    if device_ids:
        registry = dr.async_get(hass)
        wanted: set[str] = set()
        for device_id in device_ids:
            device = registry.async_get(device_id)
            if device is None:
                raise ServiceValidationError(f"Unknown device {device_id}")
            wanted.update(device.config_entries)
        entries = [entry for entry in entries if entry.entry_id in wanted]
    if not entries:
        raise ServiceValidationError("No Tuneshine is set up")
    return [entry.runtime_data.idle for entry in entries]


async def _fetch_image(hass: HomeAssistant, call: ServiceCall) -> tuple[bytes, str]:
    if camera := call.data.get(ATTR_CAMERA_ENTITY):
        from homeassistant.components.camera import async_get_image

        image = await async_get_image(hass, camera, timeout=10)
        state = hass.states.get(camera)
        return image.content, state.name if state else camera

    url = call.data[ATTR_URL]
    try:
        async with async_get_clientsession(hass).get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            response.raise_for_status()
            return await response.read(), "Image"
    except (TimeoutError, aiohttp.ClientError) as err:
        raise HomeAssistantError(f"Could not fetch {url}: {err}") from err


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Tuneshine services."""

    async def show_text(call: ServiceCall) -> None:
        for idle in _targets(hass, call):
            theme = theme_from_color(tuple(call.data.get(ATTR_COLOR, DEFAULT_ALERT_COLOR)))
            render = partial(render_text, call.data[ATTR_MESSAGE], theme=theme)
            await _alert(idle, render, call.data[ATTR_MESSAGE], call.data[ATTR_DURATION])

    async def show_image(call: ServiceCall) -> None:
        managers = _targets(hass, call)
        data, title = await _fetch_image(hass, call)
        for idle in managers:
            render = partial(render_camera, data)
            await _alert(idle, render, title, call.data[ATTR_DURATION])

    async def show_page(call: ServiceCall) -> None:
        for idle in _targets(hass, call):
            try:
                idle.async_show_page(call.data[ATTR_PAGE])
            except HomeAssistantError as err:
                raise ServiceValidationError(str(err)) from err

    async def clear(call: ServiceCall) -> None:
        for idle in _targets(hass, call):
            await idle.async_clear_alert()

    hass.services.async_register(DOMAIN, SERVICE_SHOW_TEXT, show_text, SHOW_TEXT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SHOW_IMAGE, show_image, SHOW_IMAGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SHOW_PAGE, show_page, SHOW_PAGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, clear, CLEAR_SCHEMA)


async def _alert(idle: IdleScreenManager, render, title: str, duration: float) -> None:
    try:
        await idle.async_show_alert(render, title, duration)
    except TuneshineError as err:
        raise HomeAssistantError(f"Could not update Tuneshine: {err}") from err
