# AGENTS.md

A HACS custom integration for Home Assistant. While nothing is playing, it shows Home Assistant pages (clock, weather, a random camera, templates) on a [Tuneshine](https://tuneshine.rocks), a 64×64 LED album-art display. The domain is `tuneshine`, and the code lives in `custom_components/tuneshine/`.

## Commands

```bash
uv venv --python 3.14 && uv pip install -r requirements_test.txt   # test env (pulls in homeassistant)
.venv/bin/python -m pytest tests -q                                  # tests
uvx ruff check . && uvx ruff format --check .                        # lint + format (CI runs both)
python3 scripts/preview.py preview                                   # render every page to PNGs + contact_sheet.png
python3 scripts/preview.py preview --push <device-ip>                # also cycle the frames on a real device
python3 scripts/make_icon.py                                         # regenerate brand/icon.png and icon@2x.png
```

CI (`.github/workflows/validate.yml`) runs hassfest, the HACS action and the tests on `ubuntu-26.04`. All three must pass.

## How it works

- The device has a local HTTP API (`http://<ip>/openapi.json`). The integration polls `GET /state` every 5 seconds and pushes frames with a multipart `POST /image` (a 64×64 WebP plus JSON metadata).
- Idle pages go up with `{"idle": true, "overridable": true}`. The cloud's now-playing art overrides them, and the device restores the local image by itself once playback goes idle.
- Alerts (`show_text` and `show_image`) go up with `idle: false`, so they show over the album art.
- `DELETE /image {"preserveImage": false}` hands the screen back to the stock idle image.
- Every `itemId` we push starts with `ha-`. That prefix is how `coordinator.showing_ours` tells our image from anything else.

### Device behaviour (seen on firmware 2.7.1 in cloud mode)

- The device is a small microcontroller. It drops the odd request (timeouts, `408`) and sometimes takes 2–4 seconds to answer. The coordinator only marks entities unavailable after 3 failed polls in a row, and failed pushes retry after `RETRY_DELAY × failures`.
- After music stops, the cloud can take about 2.5 minutes to mark `remoteMetadata.idle` true. That's expected.
- The cloud sometimes re-sends its stock idle image over ours. `IdleScreenManager._handle_coordinator` notices the mismatch and pushes again, with a re-check scheduled after `RESYNC_GRACE`, because the coordinator uses `always_update=False` and only notifies listeners when the state changes.

## Layout

| Path | What lives there |
| --- | --- |
| `api.py` | `TuneshineClient` (aiohttp). Raises `TuneshineConnectionError` / `TuneshineError`. |
| `coordinator.py` | Polls `/state`. Provides `is_playing`, `showing_ours`, `remote` and `local`. |
| `idle.py` | `IdleScreenManager`: page rotation loop, push/skip rules, alerts, schedule gating, resync. Most of the behaviour lives here. |
| `schedule.py` | Pure daily-window logic (`in_window`, which handles windows that cross midnight). |
| `render/` | Pure Pillow rendering, with **no Home Assistant imports**, so `scripts/preview.py` and `tests/test_render.py` run without HA. |
| `config_flow.py` | User and zeroconf (`_tuneshine._tcp.local.`) steps. The unique ID is the formatted MAC from `/state.hardwareId`. The options flow holds pages, timings, entities, templates and the schedule. |
| `services.py` / `services.yaml` | Services, registered in `async_setup`. |
| Platform files | `sensor`, `image`, `number`, `switch` (a RestoreEntity that owns the enabled state), `button`. All extend `TuneshineEntity` in `entity.py`. |

## Rules for changes

- **Keep `render/` free of Home Assistant imports.** Gather data on the event loop in `IdleScreenManager._prepare*`, then return a `functools.partial` of a pure render function. It runs in the executor via `_encode`.
- **Frames are always 64×64 RGB** and are encoded with `render.to_webp` (lossless, well under the device's 768 kB limit). Check new pages with `scripts/preview.py` and look at `contact_sheet.png` before pushing to a device.
- **Fonts are hand-drawn bitmaps** in `render/font.py` (`FONT_5X7` and `FONT_3X5`). Bold smears each pixel one to the right but skips single-pixel gaps, so `m`/`w`/`M`/`W` stay readable; keep that rule if you change glyphs. Draw text with `style.text` / `style.centered_text` for gradient fill and a shadow.
- **Colours come from `Theme`s in `render/style.py`.** Clock themes follow the hour, template pages rotate through `PAGE_THEMES`, and alerts use `theme_from_color`. There are no user colour options.
- **Weather icons** in `render/icons.py` are drawn at 4× in a 32-unit space with `Pen`, then downsampled.
- **All device writes go through `_write_lock`**, and pushes re-check `active`, the alert state and `is_playing` inside the lock. This stops an in-flight push landing after a restore; don't bypass it.
- **New user-facing strings** go in `strings.json`. Copy it to `translations/en.json`, because the two must stay identical.
- **New options** need: a constant in `const.py`, a schema field and validation in `config_flow.py`, strings, and handling in `IdleScreenManager.__init__`. Options changes reload the entry.
- **Write in British English** in user-facing text ("colour").
- **Line length is 100** (ruff, `pyproject.toml`).

## Tests

- The tests use `pytest-homeassistant-custom-component`. Use the `aioclient_mock` fixture for device HTTP and the `_mock_device` / `_calls` / `_wait_for` helpers in `tests/test_init.py`.
- The idle loop runs as a background task, so wait on the outcome with `_wait_for(...)`, not `async_block_till_done`.
- A regression test should fail on the old code. Check that before relying on it, because timing-based tests can pass for the wrong reason.

## Live testing against a real device

You can run a throwaway Home Assistant from the test venv, but the full core needs a few extras: `uv pip install --python .venv PyTurboJPEG home-assistant-frontend==<version from frontend/manifest.json>`. Without the frontend, HA boots into recovery mode and custom integrations don't load. Without turbojpeg, `camera` fails, and because `camera` is in `after_dependencies` that blocks `tuneshine` too.

1. Make a config dir with `custom_components/tuneshine` symlinked in, a minimal `configuration.yaml` (log `custom_components.tuneshine: debug`), and a pre-seeded `.storage/core.config_entries`.
2. Run `.venv/bin/python -m homeassistant -c <dir> --skip-pip`.
3. Each push is logged as `Pushed <page> page (<n> bytes)`.
4. `local_file` cameras only work as config entries now; YAML setup is rejected.
5. Make sure only one instance is running.
6. When you're done, `DELETE /image` with `{"preserveImage": false}` so the device isn't left showing a frozen clock.

## Releases

1. Bump `"version"` in `manifest.json`.
2. Push and wait for CI to pass.
3. Tag `vX.Y.Z` and create a GitHub release. HACS offers updates from releases.

Don't commit, push, tag or change the GitHub repo's settings unless asked.
