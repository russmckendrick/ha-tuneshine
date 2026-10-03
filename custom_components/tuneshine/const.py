"""Constants for the Tuneshine integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tuneshine"
MANUFACTURER: Final = "Tuneshine"

SCAN_INTERVAL: Final = timedelta(seconds=5)
REQUEST_TIMEOUT: Final = 10

CONF_PAGES: Final = "pages"
CONF_ROTATE_INTERVAL: Final = "rotate_interval"
CONF_CLOCK_24H: Final = "clock_24h"
CONF_CLOCK_SHOW_DATE: Final = "clock_show_date"
CONF_WEATHER_ENTITY: Final = "weather_entity"
CONF_CAMERA_ENTITIES: Final = "camera_entities"
CONF_CAMERA_LABEL: Final = "camera_label"
CONF_CAMERA_INTERVAL: Final = "camera_interval"
CONF_TEMPLATES: Final = "templates"
CONF_ACTIVE_FROM: Final = "active_from"
CONF_ACTIVE_TO: Final = "active_to"
CONF_ACTIVE_ENTITY: Final = "active_entity"

PAGE_CLOCK: Final = "clock"
PAGE_WEATHER: Final = "weather"
PAGE_CAMERA: Final = "camera"
PAGE_TEMPLATE: Final = "template"
PAGE_TYPES: Final = [PAGE_CLOCK, PAGE_WEATHER, PAGE_CAMERA, PAGE_TEMPLATE]

DEFAULT_PAGES: Final = [PAGE_CLOCK]
DEFAULT_ROTATE_INTERVAL: Final = 15
# Minutes between camera snapshots; 0 means every time the page comes round.
DEFAULT_CAMERA_INTERVAL: Final = 10
DEFAULT_ALERT_COLOR: Final = (255, 70, 50)

SERVICE_NAME: Final = "Home Assistant"
ITEM_PREFIX: Final = "ha-"

ATTR_MESSAGE: Final = "message"
ATTR_DURATION: Final = "duration"
ATTR_COLOR: Final = "color"
ATTR_CAMERA_ENTITY: Final = "camera_entity"
ATTR_URL: Final = "url"
ATTR_PAGE: Final = "page"
