"""Config and options flow tests."""

from __future__ import annotations

from ipaddress import ip_address

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tuneshine.const import (
    CONF_CAMERA_ENTITIES,
    CONF_PAGES,
    CONF_ROTATE_INTERVAL,
    CONF_TEMPLATES,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)

from .conftest import HOST, IDLE_STATE, MAC

DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    hostname="tuneshine-3D58.local.",
    name="Tuneshine 3D58._tuneshine._tcp.local.",
    port=80,
    type="_tuneshine._tcp.local.",
    properties={"deviceName": "Russ’s Tuneshine", "connectionMode": "cloud"},
)


async def test_user_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"http://{HOST}/state", json=IDLE_STATE)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Russ’s Tuneshine"
    assert result["data"] == {"host": HOST}
    assert result["result"].unique_id == MAC


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"http://{HOST}/state", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"http://{HOST}/state", json=IDLE_STATE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


async def test_zeroconf_updates_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, data={"host": "10.0.0.9"})
    aioclient_mock.get(f"http://{HOST}/state", json=IDLE_STATE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == HOST


async def test_options_validation(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    aioclient_mock.get(f"http://{HOST}/state", json=IDLE_STATE)
    aioclient_mock.post(f"http://{HOST}/image", json={"status": "ok"})
    aioclient_mock.delete(f"http://{HOST}/image", json={"status": "ok"})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    base = {
        CONF_ROTATE_INTERVAL: 20,
        "clock_24h": True,
        "clock_show_date": True,
        "camera_label": True,
        "camera_interval": 10,
    }

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, CONF_PAGES: ["weather"]}
    )
    assert result["errors"] == {CONF_WEATHER_ENTITY: "weather_required"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, CONF_PAGES: ["camera"]}
    )
    assert result["errors"] == {CONF_CAMERA_ENTITIES: "camera_required"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, CONF_PAGES: ["template"], CONF_TEMPLATES: ["  "]}
    )
    assert result["errors"] == {CONF_TEMPLATES: "template_required"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, CONF_PAGES: ["clock"], "active_from": "07:00:00"}
    )
    assert result["errors"] == {"active_to": "schedule_incomplete"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **base,
            CONF_PAGES: ["clock", "template"],
            CONF_TEMPLATES: ["Hi|{{ 1 + 1 }}"],
            "active_from": "07:00:00",
            "active_to": "23:00:00",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_TEMPLATES] == ["Hi|{{ 1 + 1 }}"]
    assert config_entry.options[CONF_ROTATE_INTERVAL] == 20
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)
