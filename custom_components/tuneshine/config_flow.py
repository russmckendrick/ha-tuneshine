"""Config flow for Tuneshine."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import TuneshineClient, TuneshineError
from .const import (
    CONF_ACTIVE_ENTITY,
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_TO,
    CONF_ANIMATE,
    CONF_CAMERA_ENTITIES,
    CONF_CAMERA_INTERVAL,
    CONF_CAMERA_LABEL,
    CONF_CLOCK_24H,
    CONF_CLOCK_SHOW_DATE,
    CONF_PAGES,
    CONF_ROTATE_INTERVAL,
    CONF_TEMPLATES,
    CONF_WEATHER_ENTITY,
    DEFAULT_ANIMATE,
    DEFAULT_CAMERA_INTERVAL,
    DEFAULT_PAGES,
    DEFAULT_ROTATE_INTERVAL,
    DOMAIN,
    PAGE_CAMERA,
    PAGE_TEMPLATE,
    PAGE_TYPES,
    PAGE_WEATHER,
)

_LOGGER = logging.getLogger(__name__)


class TuneshineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tuneshine."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None

    async def _async_probe(self, host: str) -> dict[str, Any]:
        client = TuneshineClient(async_get_clientsession(self.hass), host)
        return await client.get_state()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up by entering a host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                state = await self._async_probe(host)
            except TuneshineError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(format_mac(state["hardwareId"]))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=state.get("name") or "Tuneshine",
                    data={CONF_HOST: host},
                    options={CONF_PAGES: DEFAULT_PAGES},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Set up from mDNS discovery."""
        host = discovery_info.host
        try:
            state = await self._async_probe(host)
        except TuneshineError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(format_mac(state["hardwareId"]))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._name = state.get("name") or discovery_info.properties.get("deviceName") or "Tuneshine"
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or "Tuneshine",
                data={CONF_HOST: self._host},
                options={CONF_PAGES: DEFAULT_PAGES},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._name or "Tuneshine", "host": self._host or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TuneshineOptionsFlow:
        return TuneshineOptionsFlow()


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    def suggested(key: str, default: Any = None) -> dict[str, Any]:
        return {"suggested_value": options.get(key, default)}

    return vol.Schema(
        {
            vol.Required(
                CONF_PAGES, default=options.get(CONF_PAGES, DEFAULT_PAGES)
            ): SelectSelector(
                SelectSelectorConfig(options=PAGE_TYPES, multiple=True, translation_key="pages")
            ),
            vol.Required(
                CONF_ROTATE_INTERVAL,
                default=options.get(CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5, max=600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_ANIMATE, default=options.get(CONF_ANIMATE, DEFAULT_ANIMATE)
            ): BooleanSelector(),
            vol.Required(
                CONF_CLOCK_24H, default=options.get(CONF_CLOCK_24H, True)
            ): BooleanSelector(),
            vol.Required(
                CONF_CLOCK_SHOW_DATE, default=options.get(CONF_CLOCK_SHOW_DATE, True)
            ): BooleanSelector(),
            vol.Optional(
                CONF_WEATHER_ENTITY, description=suggested(CONF_WEATHER_ENTITY)
            ): EntitySelector(EntitySelectorConfig(domain="weather")),
            vol.Optional(
                CONF_CAMERA_ENTITIES, description=suggested(CONF_CAMERA_ENTITIES)
            ): EntitySelector(EntitySelectorConfig(domain="camera", multiple=True)),
            vol.Required(
                CONF_CAMERA_INTERVAL,
                default=options.get(CONF_CAMERA_INTERVAL, DEFAULT_CAMERA_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=1440, step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_CAMERA_LABEL, default=options.get(CONF_CAMERA_LABEL, True)
            ): BooleanSelector(),
            vol.Optional(CONF_TEMPLATES, description=suggested(CONF_TEMPLATES)): TextSelector(
                TextSelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_ACTIVE_FROM, description=suggested(CONF_ACTIVE_FROM)): TimeSelector(),
            vol.Optional(CONF_ACTIVE_TO, description=suggested(CONF_ACTIVE_TO)): TimeSelector(),
            vol.Optional(
                CONF_ACTIVE_ENTITY, description=suggested(CONF_ACTIVE_ENTITY)
            ): EntitySelector(),
        }
    )


class TuneshineOptionsFlow(OptionsFlow):
    """Choose what the idle screen shows."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            pages = user_input.get(CONF_PAGES, [])
            templates = [t for t in user_input.get(CONF_TEMPLATES) or [] if t.strip()]
            user_input[CONF_TEMPLATES] = templates
            if not pages:
                errors[CONF_PAGES] = "no_pages"
            elif PAGE_WEATHER in pages and not user_input.get(CONF_WEATHER_ENTITY):
                errors[CONF_WEATHER_ENTITY] = "weather_required"
            elif PAGE_CAMERA in pages and not user_input.get(CONF_CAMERA_ENTITIES):
                errors[CONF_CAMERA_ENTITIES] = "camera_required"
            elif PAGE_TEMPLATE in pages and not templates:
                errors[CONF_TEMPLATES] = "template_required"
            elif bool(user_input.get(CONF_ACTIVE_FROM)) != bool(user_input.get(CONF_ACTIVE_TO)):
                errors[CONF_ACTIVE_TO] = "schedule_incomplete"
            else:
                user_input[CONF_ROTATE_INTERVAL] = int(user_input[CONF_ROTATE_INTERVAL])
                user_input[CONF_CAMERA_INTERVAL] = int(user_input[CONF_CAMERA_INTERVAL])
                return self.async_create_entry(data=user_input)
            options = user_input
        else:
            options = dict(self.config_entry.options)

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(options), errors=errors
        )
