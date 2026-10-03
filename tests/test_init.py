"""Setup, entities, idle screen and service tests."""

from __future__ import annotations

import asyncio
import io
import json
import time
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tuneshine.const import DOMAIN

from .conftest import HOST, IDLE_STATE, MAC, playing_state

URL_STATE = f"http://{HOST}/state"
URL_IMAGE = f"http://{HOST}/image"


def _mock_device(aioclient_mock: AiohttpClientMocker, state: dict[str, Any]) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_STATE, json=state)
    aioclient_mock.post(URL_IMAGE, json={"status": "ok"})
    aioclient_mock.delete(URL_IMAGE, json={"status": "ok"})
    aioclient_mock.post(f"http://{HOST}/brightness", json={"status": "ok"})


def _calls(aioclient_mock: AiohttpClientMocker, method: str, url: str) -> list:
    return [call for call in aioclient_mock.mock_calls if call[0] == method and str(call[1]) == url]


def _metadata(call) -> dict[str, Any]:
    form = call[2]
    for options, _headers, value in form._fields:
        if options.get("name") == "metadata":
            return json.loads(value)
    raise AssertionError("no metadata in upload")


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.01)


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{MAC}_{key}")
    assert entity_id
    return entity_id


async def _setup(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED


async def test_pushes_idle_page(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)

    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE))
    metadata = _metadata(_calls(aioclient_mock, "POST", URL_IMAGE)[0])
    assert metadata["idle"] is True
    assert metadata["overridable"] is True
    assert metadata["itemId"] == "ha-clock"

    assert hass.states.get(_entity_id(hass, "switch", "idle_screen")).state == "on"
    assert hass.states.get(_entity_id(hass, "sensor", "idle_page")).state == "clock"
    assert hass.states.get(_entity_id(hass, "number", "active_brightness")).state == "100"

    await hass.config_entries.async_unload(config_entry.entry_id)
    deletes = _calls(aioclient_mock, "DELETE", URL_IMAGE)
    assert deletes and deletes[-1][2] == {"preserveImage": False}


async def test_skips_push_while_playing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    _mock_device(aioclient_mock, playing_state())
    await _setup(hass, config_entry)
    await asyncio.sleep(0.2)
    assert not _calls(aioclient_mock, "POST", URL_IMAGE)

    now_playing = hass.states.get(_entity_id(hass, "sensor", "now_playing"))
    assert now_playing.state == "Shout"
    assert now_playing.attributes["artist"] == "Tears for Fears"

    # Playback stops: the next poll should trigger a push straight away.
    _mock_device(aioclient_mock, IDLE_STATE)
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE))
    assert hass.states.get(_entity_id(hass, "sensor", "now_playing")).state == "unknown"
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_switch_off_restores_device_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE))

    switch = _entity_id(hass, "switch", "idle_screen")
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "off"
    assert _calls(aioclient_mock, "DELETE", URL_IMAGE)[-1][2] == {"preserveImage": False}

    posts = len(_calls(aioclient_mock, "POST", URL_IMAGE))
    config_entry.runtime_data.idle.async_next_page()
    await asyncio.sleep(0.1)
    assert len(_calls(aioclient_mock, "POST", URL_IMAGE)) == posts
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_show_text_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    _mock_device(aioclient_mock, playing_state())
    await _setup(hass, config_entry)

    await hass.services.async_call(
        DOMAIN, "show_text", {"message": "Doorbell!", "duration": 1}, blocking=True
    )
    posts = _calls(aioclient_mock, "POST", URL_IMAGE)
    assert len(posts) == 1
    metadata = _metadata(posts[0])
    assert metadata["idle"] is False
    assert metadata["trackName"] == "Doorbell!"

    # Music is still playing when the alert ends, so hand back to the artwork.
    await _wait_for(lambda: _calls(aioclient_mock, "DELETE", URL_IMAGE), timeout=3)
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_brightness(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity_id(hass, "number", "idle_brightness"), "value": 35},
        blocking=True,
    )
    call = _calls(aioclient_mock, "POST", f"http://{HOST}/brightness")[-1]
    assert call[2] == {"idle": 35}
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_setup_retries_when_offline(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    aioclient_mock.get(URL_STATE, exc=TimeoutError)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_condition_entity_gates_screen(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    hass.states.async_set("input_boolean.tuneshine_pages", "off")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data={"host": HOST},
        options={"pages": ["clock"], "active_entity": "input_boolean.tuneshine_pages"},
    )
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    await asyncio.sleep(0.2)
    assert not _calls(aioclient_mock, "POST", URL_IMAGE)
    assert hass.states.get(_entity_id(hass, "sensor", "idle_page")).state == "unknown"

    hass.states.async_set("input_boolean.tuneshine_pages", "on")
    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE))
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, "sensor", "idle_page")).state == "clock"

    # Turning the condition off hands the screen back to the device.
    hass.states.async_set("input_boolean.tuneshine_pages", "off")
    await _wait_for(lambda: _calls(aioclient_mock, "DELETE", URL_IMAGE))
    assert _calls(aioclient_mock, "DELETE", URL_IMAGE)[-1][2] == {"preserveImage": False}
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_repushes_when_cloud_replaces_our_page(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry, monkeypatch
) -> None:
    """The cloud re-sending its idle image inside the grace window still gets corrected."""
    monkeypatch.setattr("custom_components.tuneshine.idle.RESYNC_GRACE", 0.3)
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE))
    pushes = len(_calls(aioclient_mock, "POST", URL_IMAGE))

    # Straight after our push, /state shows the cloud's idle image instead.
    replaced = {**IDLE_STATE, "localMetadata": {"itemId": "ha-clock", "idle": True}}
    replaced["remoteMetadata"] = {**IDLE_STATE["remoteMetadata"], "itemId": "OTHER_IDLE"}
    _mock_device(aioclient_mock, replaced)
    config_entry.runtime_data.idle._last_push = time.monotonic()
    await config_entry.runtime_data.coordinator.async_refresh()
    assert not _calls(aioclient_mock, "POST", URL_IMAGE)

    # No further state changes arrive, but the page is pushed again after the grace period.
    await _wait_for(lambda: _calls(aioclient_mock, "POST", URL_IMAGE), timeout=3)
    assert pushes >= 1
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_camera_interval_reuses_snapshot_and_skips_page(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Battery cameras are only woken every camera_interval minutes."""
    hass.states.async_set("camera.front", "idle", {"friendly_name": "Front"})
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data={"host": HOST},
        options={
            "pages": ["clock", "camera"],
            "camera_entities": ["camera.front"],
            "camera_interval": 10,
        },
    )
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    idle = config_entry.runtime_data.idle
    clock, camera = idle.pages

    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), (200, 30, 30)).save(buffer, format="JPEG")
    fetch = AsyncMock(return_value=buffer.getvalue())
    idle._fetch_snapshot = fetch

    # No snapshot yet, so the camera page is due.
    idle._index = 0
    assert idle._next_index() == 1
    await idle._prepare(camera)
    await idle._prepare(camera)
    assert fetch.await_count == 1

    # Within the interval the rotation skips the camera page.
    idle._index = 0
    assert idle._next_index() == 0

    # Once the interval has passed it comes round again with a fresh snapshot.
    idle._camera_fetched_at -= 10 * 60
    assert idle._next_index() == 1
    await idle._prepare(camera)
    assert fetch.await_count == 2
    assert clock.kind == "clock"
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_camera_interval_zero_always_fetches(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    hass.states.async_set("camera.front", "idle")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data={"host": HOST},
        options={"pages": ["camera"], "camera_entities": ["camera.front"], "camera_interval": 0},
    )
    _mock_device(aioclient_mock, IDLE_STATE)
    await _setup(hass, config_entry)
    idle = config_entry.runtime_data.idle
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buffer, format="JPEG")
    idle._fetch_snapshot = AsyncMock(return_value=buffer.getvalue())
    await idle._prepare(idle.pages[0])
    await idle._prepare(idle.pages[0])
    assert idle._fetch_snapshot.await_count == 2
    await hass.config_entries.async_unload(config_entry.entry_id)
