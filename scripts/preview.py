"""Render every page type with sample data to PNGs for checking designs.

    python scripts/preview.py [output_dir] [--push HOST]

Each frame is saved at 64x64 and as an 8x upscale with an LED-style grid, plus
a contact sheet of everything. --push sends each frame to a Tuneshine in turn.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tuneshine"))

from render import render_camera, render_clock, render_text, render_weather, to_webp
from render.text import theme_from_color
from render.weather import ICONS

SCALE = 8


def sample_camera() -> bytes:
    """A fake 16:9 'camera' frame with a gradient sky and a house."""
    image = Image.new("RGB", (640, 360))
    draw = ImageDraw.Draw(image)
    for y in range(360):
        draw.line((0, y, 640, y), fill=(40 + y // 4, 90 + y // 5, 200 - y // 3))
    draw.rectangle((0, 260, 640, 360), fill=(40, 120, 40))
    draw.rectangle((250, 160, 390, 280), fill=(190, 150, 110))
    draw.polygon([(235, 165), (320, 95), (405, 165)], fill=(150, 40, 40))
    draw.rectangle((305, 220, 335, 280), fill=(80, 50, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def frames() -> dict[str, Image.Image]:
    now = datetime(2026, 10, 3, 9, 41, tzinfo=UTC)
    result = {
        f"clock_{hour:02d}": render_clock(now.replace(hour=hour)) for hour in (2, 6, 9, 13, 18, 22)
    }
    result["clock_12h"] = render_clock(now.replace(hour=21), use_24h=False)
    result["clock_wednesday"] = render_clock(now.replace(day=7, hour=15))
    result["clock_no_date"] = render_clock(now, show_date=False)
    result["camera"] = render_camera(sample_camera(), label="Front door")
    texts = [
        "21.5°",
        "Office|21.5°C",
        "Solar|3.2 kW",
        "Washing machine|Finished 10 minutes ago",
        "Bins|Recycling tomorrow",
        "The quick brown fox jumps over the lazy dog while the dishwasher hums along quietly",
    ]
    for index, value in enumerate(texts):
        result[f"text_{index}"] = render_text(value, theme=index)
    result["text_alert"] = render_text("Doorbell!", theme=theme_from_color((255, 60, 60)))
    temps = [(18, 21, 12), (-3, 1, -6), (27, 31, 15), (8, 11, 4), (None, None, None)]
    for i, condition in enumerate(ICONS):
        temp, high, low = temps[i % len(temps)]
        result[f"weather_{condition}"] = render_weather(condition, temp, high=high, low=low)
    return result


def led(image: Image.Image) -> Image.Image:
    """Upscale with a dark gap between pixels, roughly how the matrix looks."""
    big = image.resize((64 * SCALE, 64 * SCALE), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(big)
    for i in range(0, 64 * SCALE, SCALE):
        draw.line((i, 0, i, 64 * SCALE), fill=(12, 12, 12))
        draw.line((0, i, 64 * SCALE, i), fill=(12, 12, 12))
    return big


def push(host: str, name: str, image: Image.Image) -> None:
    boundary = uuid.uuid4().hex
    metadata = json.dumps(
        {"idle": True, "overridable": True, "trackName": name, "serviceName": "Preview"}
    )
    body = b"".join(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="frame.webp"\r\n'
            "Content-Type: image/webp\r\n\r\n".encode(),
            to_webp(image),
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n{metadata}\r\n'
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        f"http://{host}/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(f"pushed {name}: {response.read().decode()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="preview")
    parser.add_argument("--push", metavar="HOST", help="send each frame to this Tuneshine")
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between pushed frames")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rendered = frames()

    columns = 6
    rows = -(-len(rendered) // columns)
    tile = 64 * 4 + 8
    sheet = Image.new("RGB", (columns * tile, rows * tile), (30, 30, 30))
    for index, (name, image) in enumerate(rendered.items()):
        assert image.size == (64, 64), name
        webp = to_webp(image)
        image.save(out / f"{name}.png")
        led(image).save(out / f"{name}@8x.png")
        print(f"{name}: {len(webp)} bytes webp")
        thumb = image.resize((64 * 4, 64 * 4), Image.Resampling.NEAREST)
        sheet.paste(thumb, ((index % columns) * tile + 4, (index // columns) * tile + 4))
    sheet.save(out / "contact_sheet.png")
    print(f"wrote {len(rendered)} frames to {out}/")

    if args.push:
        for name, image in rendered.items():
            push(args.push, name, image)
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
