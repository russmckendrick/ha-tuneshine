"""Fixtures for Tuneshine tests."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuneshine.const import CONF_PAGES, DOMAIN

HOST = "192.168.50.133"
MAC = "24:58:7c:d1:3d:58"

IDLE_STATE: dict[str, Any] = {
    "name": "Russ’s Tuneshine",
    "firmwareVersion": "2.7.1",
    "hardwareId": MAC,
    "mode": "cloud",
    "createdAt": None,
    "wifi": {"ssid": "Deckard", "status": "connected"},
    "config": {
        "brightness": {"base": 20, "active": 100, "idle": 20},
        "animation": "crate",
        "effect": "none",
        "sendDiagnostics": True,
        "preserveArtwork": False,
    },
    "imageSource": "remote",
    "localMetadata": None,
    "remoteMetadata": {
        "itemId": "BOTTOM_LINE",
        "imageUrl": "https://services.tuneshine.rocks/static/idle-images/bottomline.webp",
        "idle": True,
        "lastImageError": None,
    },
}


def playing_state() -> dict[str, Any]:
    state = copy.deepcopy(IDLE_STATE)
    state["remoteMetadata"] = {
        "trackName": "Shout",
        "artistName": "Tears for Fears",
        "albumName": "Songs from the Big Chair",
        "serviceName": "applemusic",
        "itemId": "i.vpB51HmRWB6",
        "imageUrl": "https://example.com/art.jpg",
        "contentType": "track",
        "idle": False,
        "lastImageError": None,
    }
    return state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom integrations in every test."""
    yield


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Russ’s Tuneshine",
        unique_id=MAC,
        data={"host": HOST},
        options={CONF_PAGES: ["clock"]},
    )
