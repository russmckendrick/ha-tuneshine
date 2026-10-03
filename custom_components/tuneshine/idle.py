"""Rotates Home Assistant pages on the Tuneshine while nothing is playing.

Pages are pushed as local idle images marked overridable, so the Tuneshine
cloud's now-playing artwork replaces them as soon as music starts, and the
device restores the last page by itself once playback goes idle again. We
also stop pushing while music plays, and push a fresh page straight away when
it stops so the clock isn't stale.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
from PIL import Image

from .api import TuneshineClient, TuneshineError
from .const import (
    CONF_ACTIVE_ENTITY,
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_TO,
    CONF_CAMERA_ENTITIES,
    CONF_CAMERA_INTERVAL,
    CONF_CAMERA_LABEL,
    CONF_CLOCK_24H,
    CONF_CLOCK_SHOW_DATE,
    CONF_PAGES,
    CONF_ROTATE_INTERVAL,
    CONF_TEMPLATES,
    CONF_WEATHER_ENTITY,
    DEFAULT_CAMERA_INTERVAL,
    DEFAULT_PAGES,
    DEFAULT_ROTATE_INTERVAL,
    ITEM_PREFIX,
    PAGE_CAMERA,
    PAGE_CLOCK,
    PAGE_TEMPLATE,
    PAGE_WEATHER,
    SERVICE_NAME,
)
from .coordinator import TuneshineCoordinator
from .render import render_camera, render_clock, render_text, render_weather, to_webp
from .schedule import ACTIVE_STATES, in_window, parse_time

_LOGGER = logging.getLogger(__name__)

FORECAST_TTL = timedelta(minutes=30)
# Wait this long after a push before trusting /state to show it.
RESYNC_GRACE = 15.0
# Re-check now and then while music plays, in case a wake-up is missed.
PLAYING_RECHECK = 60.0
# Failed pushes are retried after this many seconds (times the failure count).
RETRY_DELAY = 3.0
# Only warn once pushes have failed this many times in a row.
WARN_AFTER_FAILURES = 3


@dataclass(frozen=True)
class Page:
    """One page in the idle rotation."""

    key: str
    kind: str
    title: str
    template: str | None = None


def build_pages(options: dict[str, Any]) -> list[Page]:
    """Turn the options into an ordered list of pages."""
    pages: list[Page] = []
    for kind in options.get(CONF_PAGES, DEFAULT_PAGES):
        if kind == PAGE_CLOCK:
            pages.append(Page(PAGE_CLOCK, PAGE_CLOCK, "Clock"))
        elif kind == PAGE_WEATHER and options.get(CONF_WEATHER_ENTITY):
            pages.append(Page(PAGE_WEATHER, PAGE_WEATHER, "Weather"))
        elif kind == PAGE_CAMERA and options.get(CONF_CAMERA_ENTITIES):
            pages.append(Page(PAGE_CAMERA, PAGE_CAMERA, "Camera"))
        elif kind == PAGE_TEMPLATE:
            for index, template in enumerate(options.get(CONF_TEMPLATES) or []):
                if template.strip():
                    pages.append(
                        Page(
                            f"{PAGE_TEMPLATE}_{index + 1}",
                            PAGE_TEMPLATE,
                            f"Template {index + 1}",
                            template,
                        )
                    )
    return pages


def _encode(render: Callable[[], Image.Image]) -> bytes:
    return to_webp(render())


class IdleScreenManager:
    """Owns what the integration shows on the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TuneshineClient,
        coordinator: TuneshineCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.coordinator = coordinator
        self.options = dict(entry.options)
        self.pages = build_pages(self.options)
        self.enabled = False

        self._index = 0
        self._rotate_at = 0.0
        self._wake = asyncio.Event()
        # Serialises writes so an in-flight push can't land after a restore.
        self._write_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._unsub_coordinator: CALLBACK_TYPE | None = None
        self._unsub_condition: CALLBACK_TYPE | None = None
        self._unsub_recheck: CALLBACK_TYPE | None = None
        self._active_from = parse_time(self.options.get(CONF_ACTIVE_FROM))
        self._active_to = parse_time(self.options.get(CONF_ACTIVE_TO))
        self._condition_entity: str | None = self.options.get(CONF_ACTIVE_ENTITY)
        self._was_active = False
        # True while one of our pages may be on the device.
        self._ours_on_device = False
        self._listeners: list[CALLBACK_TYPE] = []

        self._alert_until: float | None = None
        self._last_hash: str | None = None
        self._last_page_key: str | None = None
        self._last_push = 0.0
        self._was_playing = False
        self._push_failures = 0
        self._failed_pages: set[str] = set()
        self._last_camera: str | None = None
        # The last snapshot, reused until the camera interval has passed.
        self._camera_snapshot: tuple[bytes, str | None] | None = None
        self._camera_fetched_at = 0.0
        self._forecast: dict[str, tuple[float, float | None, float | None]] = {}

    # ----------------------------------------------------------------- lifecycle

    @callback
    def async_start(self) -> None:
        """Start the rotation task."""
        self._was_playing = self.coordinator.is_playing
        self._unsub_coordinator = self.coordinator.async_add_listener(self._handle_coordinator)
        if self._condition_entity:
            self._unsub_condition = async_track_state_change_event(
                self.hass, self._condition_entity, self._handle_condition
            )
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), f"tuneshine idle screen {self.client.host}"
        )

    async def async_stop(self) -> None:
        """Stop rotating and hand the screen back to the device."""
        for unsub in (self._unsub_coordinator, self._unsub_condition, self._unsub_recheck):
            if unsub:
                unsub()
        self._unsub_coordinator = self._unsub_condition = self._unsub_recheck = None
        if self._task:
            self._task.cancel()
            self._task = None
        if self._ours_on_device or self._alert_until is not None:
            await self._restore_device_idle()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Listen for page changes."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    def schedule(self) -> tuple[bool, float | None]:
        """Whether the schedule and condition allow the screen, and seconds until that may change."""
        active, next_change = in_window(dt_util.now(), self._active_from, self._active_to)
        if self._condition_entity:
            state = self.hass.states.get(self._condition_entity)
            active = active and state is not None and state.state in ACTIVE_STATES
        if next_change is None:
            return active, None
        return active, max((next_change - dt_util.now()).total_seconds(), 0.0) + 0.5

    @property
    def active(self) -> bool:
        """True when the switch is on and the schedule allows it."""
        return self.enabled and bool(self.pages) and self.schedule()[0]

    @property
    def current_page(self) -> Page | None:
        """The page currently in the rotation, if any."""
        if not self.pages:
            return None
        return self.pages[self._index % len(self.pages)]

    # ------------------------------------------------------------------ controls

    async def async_set_enabled(self, enabled: bool) -> None:
        """Turn the idle screen on or off."""
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self._last_hash = None
        if not enabled and self._alert_until is None:
            await self._restore_device_idle()
        self._notify()
        self._wake.set()

    @callback
    def async_next_page(self) -> None:
        """Skip to the next page now."""
        self._index = self._next_index()
        self._rotate_at = time.monotonic() + self._interval
        self._notify()
        self._wake.set()

    @callback
    def async_show_page(self, key: str) -> None:
        """Jump to a page by key, e.g. 'clock' or 'template_2'."""
        for index, page in enumerate(self.pages):
            if key in (page.key, page.kind):
                self._index = index
                self._rotate_at = time.monotonic() + self._interval
                self._notify()
                self._wake.set()
                return
        raise HomeAssistantError(f"No page '{key}' is configured")

    async def async_show_alert(
        self, render: Callable[[], Image.Image], title: str, duration: float
    ) -> None:
        """Show a frame over everything, music included, for a while."""
        webp = await self.hass.async_add_executor_job(_encode, render)
        async with self._write_lock:
            await self._post_alert(webp, title, duration)

    async def _post_alert(self, webp: bytes, title: str, duration: float) -> None:
        await self.client.post_image(
            webp,
            {
                "idle": False,
                "trackName": title,
                "serviceName": SERVICE_NAME,
                "itemId": f"{ITEM_PREFIX}alert-{int(time.time())}",
            },
        )
        self._alert_until = time.monotonic() + duration
        self._last_hash = None
        self._ours_on_device = True
        self._wake.set()

    async def async_clear_alert(self) -> None:
        """End any alert early."""
        if self._alert_until is not None:
            self._alert_until = time.monotonic()
            self._wake.set()

    # ---------------------------------------------------------------- internals

    @property
    def _interval(self) -> float:
        return float(self.options.get(CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL))

    @property
    def _camera_due(self) -> bool:
        """Whether it's time for a fresh camera snapshot."""
        minutes = float(self.options.get(CONF_CAMERA_INTERVAL, DEFAULT_CAMERA_INTERVAL))
        return (
            self._camera_snapshot is None
            or time.monotonic() - self._camera_fetched_at >= minutes * 60
        )

    def _next_index(self) -> int:
        """The next page in the rotation, skipping the camera until it's due."""
        if not self.pages:
            return 0
        for step in range(1, len(self.pages) + 1):
            index = (self._index + step) % len(self.pages)
            if self.pages[index].kind != PAGE_CAMERA or self._camera_due:
                return index
        # Only the camera page and it isn't due: stay put and reuse the snapshot.
        return self._index

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _handle_coordinator(self) -> None:
        playing = self.coordinator.is_playing
        if self._was_playing and not playing:
            _LOGGER.debug("Playback went idle, refreshing idle screen")
            self._last_hash = None
            self._wake.set()
        elif (
            self.active
            and not playing
            and self._alert_until is None
            and self.coordinator.last_update_success
            and not self.coordinator.showing_ours
        ):
            # The device rebooted, or the Tuneshine cloud re-sent its own idle
            # image over ours. Right after a push /state can simply be stale, so
            # wait out the grace period; listeners only fire when the state
            # changes, so schedule a re-check rather than dropping it.
            since_push = time.monotonic() - self._last_push
            if since_push > RESYNC_GRACE:
                _LOGGER.debug("Idle screen missing from device, pushing again")
                self._last_hash = None
                self._wake.set()
            elif self._unsub_recheck is None:
                self._unsub_recheck = async_call_later(
                    self.hass, RESYNC_GRACE - since_push + 0.1, self._recheck
                )
        self._was_playing = playing

    @callback
    def _recheck(self, _now: Any) -> None:
        self._unsub_recheck = None
        self._handle_coordinator()

    @callback
    def _handle_condition(self, event: Event[EventStateChangedData]) -> None:
        self._wake.set()

    async def _sleep(self, timeout: float | None) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except TimeoutError:
            pass
        self._wake.clear()

    async def _run(self) -> None:
        self._rotate_at = time.monotonic() + self._interval
        while True:
            now = time.monotonic()

            if self._alert_until is not None:
                if now < self._alert_until:
                    await self._sleep(self._alert_until - now)
                    continue
                self._alert_until = None
                if not self.active or self.coordinator.is_playing:
                    # Let the device go back to artwork or its own idle image.
                    await self._restore_device_idle()
                continue

            allowed, change_in = self.schedule()
            active = self.enabled and bool(self.pages) and allowed
            if active != self._was_active:
                self._was_active = active
                self._last_hash = None
                self._notify()
            if not active:
                if self._ours_on_device:
                    _LOGGER.debug("Idle screen outside its schedule, handing back to device")
                    await self._restore_device_idle()
                await self._sleep(change_in)
                continue

            if now >= self._rotate_at:
                self._index = self._next_index()
                self._rotate_at = now + self._interval
                self._notify()

            if self.coordinator.is_playing:
                await self._sleep(PLAYING_RECHECK)
                continue

            page = self.pages[self._index % len(self.pages)]
            await self._push(page)

            timeout = self._rotate_at - time.monotonic()
            if page.kind == PAGE_CLOCK:
                local = dt_util.now()
                to_next_minute = 60 - local.second - local.microsecond / 1_000_000 + 0.2
                timeout = min(timeout, to_next_minute)
            if self._push_failures:
                # The device drops the odd request; try again shortly.
                timeout = min(timeout, RETRY_DELAY * self._push_failures)
            if change_in is not None:
                timeout = min(timeout, change_in)
            await self._sleep(max(timeout, 1.0))

    async def _push(self, page: Page) -> None:
        try:
            render = await self._prepare(page)
            webp = await self.hass.async_add_executor_job(_encode, render)
        except Exception as err:  # noqa: BLE001 - one bad page must not stop the rotation
            if page.key not in self._failed_pages:
                _LOGGER.warning("Could not render %s page: %s", page.title, err)
                self._failed_pages.add(page.key)
            return
        self._failed_pages.discard(page.key)

        digest = hashlib.sha1(webp, usedforsecurity=False).hexdigest()
        if digest == self._last_hash:
            return

        async with self._write_lock:
            # Things may have changed while rendering (switch off, alert, music).
            if not self.active or self._alert_until is not None or self.coordinator.is_playing:
                return
            await self._post_page(page, webp, digest)

    async def _post_page(self, page: Page, webp: bytes, digest: str) -> None:
        same_page = page.key == self._last_page_key
        try:
            await self.client.post_image(
                webp,
                {
                    "idle": True,
                    "overridable": True,
                    "trackName": page.title,
                    "serviceName": SERVICE_NAME,
                    "itemId": f"{ITEM_PREFIX}{page.key}",
                    "animation": "none" if same_page else "dissolve",
                },
            )
        except TuneshineError as err:
            self._push_failures += 1
            log = _LOGGER.warning if self._push_failures == WARN_AFTER_FAILURES else _LOGGER.debug
            log("Could not update Tuneshine idle screen: %s", err)
            return
        if self._push_failures >= WARN_AFTER_FAILURES:
            _LOGGER.info("Tuneshine idle screen updates working again")
        self._push_failures = 0
        _LOGGER.debug("Pushed %s page (%d bytes)", page.title, len(webp))
        self._last_hash = digest
        self._last_page_key = page.key
        self._last_push = time.monotonic()
        self._ours_on_device = True

    async def _restore_device_idle(self) -> None:
        async with self._write_lock:
            self._last_hash = None
            self._last_page_key = None
            self._ours_on_device = False
            try:
                await self.client.delete_image(preserve_image=False)
            except TuneshineError as err:
                _LOGGER.debug("Could not clear Tuneshine image: %s", err)

    # ------------------------------------------------------------------- pages

    async def _prepare(self, page: Page) -> Callable[[], Image.Image]:
        """Gather data on the event loop; return a pure render for the executor."""
        if page.kind == PAGE_CLOCK:
            return partial(
                render_clock,
                dt_util.now(),
                use_24h=self.options.get(CONF_CLOCK_24H, True),
                show_date=self.options.get(CONF_CLOCK_SHOW_DATE, True),
            )
        if page.kind == PAGE_WEATHER:
            return await self._prepare_weather()
        if page.kind == PAGE_CAMERA:
            return await self._prepare_camera()
        if page.kind == PAGE_TEMPLATE and page.template:
            text = self.render_template(page.template)
            # Each template page gets its own colour scheme.
            return partial(render_text, text, theme=int(page.key.rsplit("_", 1)[1]) - 1)
        raise HomeAssistantError(f"Unknown page {page.key}")

    def render_template(self, template: str) -> str:
        try:
            return str(Template(template, self.hass).async_render(parse_result=False))
        except TemplateError as err:
            raise HomeAssistantError(f"template error: {err}") from err

    async def _prepare_weather(self) -> Callable[[], Image.Image]:
        entity_id = self.options[CONF_WEATHER_ENTITY]
        state = self.hass.states.get(entity_id)
        if state is None:
            raise HomeAssistantError(f"{entity_id} not found")
        condition = state.state
        sun = self.hass.states.get("sun.sun")
        if condition == "partlycloudy" and sun and sun.state == "below_horizon":
            condition = "partlycloudy-night"
        temperature = state.attributes.get("temperature")
        high, low = await self._daily_high_low(entity_id)
        return partial(
            render_weather,
            condition,
            float(temperature) if temperature is not None else None,
            high=high,
            low=low,
            celsius=state.attributes.get("temperature_unit") != "°F",
        )

    async def _daily_high_low(self, entity_id: str) -> tuple[float | None, float | None]:
        cached = self._forecast.get(entity_id)
        if cached and time.monotonic() - cached[0] < FORECAST_TTL.total_seconds():
            return cached[1], cached[2]
        high = low = None
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "daily"},
                blocking=True,
                return_response=True,
            )
            forecast = ((response or {}).get(entity_id) or {}).get("forecast") or []
            if forecast:
                high = forecast[0].get("temperature")
                low = forecast[0].get("templow")
        except HomeAssistantError as err:
            _LOGGER.debug("No daily forecast for %s: %s", entity_id, err)
        self._forecast[entity_id] = (time.monotonic(), high, low)
        return high, low

    async def _prepare_camera(self) -> Callable[[], Image.Image]:
        if not self._camera_due and self._camera_snapshot is not None:
            # Battery cameras can wake up for every snapshot, so reuse the last one.
            content, label = self._camera_snapshot
            return partial(render_camera, content, label=label)

        cameras = [
            entity_id
            for entity_id in self.options.get(CONF_CAMERA_ENTITIES, [])
            if (state := self.hass.states.get(entity_id)) and state.state != "unavailable"
        ]
        if not cameras:
            raise HomeAssistantError("no cameras available")
        choices = [c for c in cameras if c != self._last_camera] or cameras
        entity_id = random.choice(choices)
        self._last_camera = entity_id
        content = await self._fetch_snapshot(entity_id)
        label = None
        if self.options.get(CONF_CAMERA_LABEL, True) and (state := self.hass.states.get(entity_id)):
            label = state.name
        self._camera_snapshot = (content, label)
        self._camera_fetched_at = time.monotonic()
        return partial(render_camera, content, label=label)

    async def _fetch_snapshot(self, entity_id: str) -> bytes:
        from homeassistant.components.camera import async_get_image

        return (await async_get_image(self.hass, entity_id, timeout=10)).content
