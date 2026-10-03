"""Render every page type with sample data to PNGs for checking designs.

    python scripts/preview.py [output_dir] [--still] [--push [HOST]]

Each frame is saved at 64x64 and as an 8x upscale with an LED-style grid.
Animated pages are also saved as the WebP sent to the device and an 8x GIF; their
PNGs show the first frame. contact_sheet.png shows every page still (as with
animation turned off) and contact_sheet.webp plays the animated ones.
--still renders, and pushes, the still pages only. --push sends each frame to a Tuneshine in turn;
without a HOST it finds one on the network over mDNS.
"""

from __future__ import annotations

import argparse
import io
import json
import socket
import struct
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tuneshine"))

from render import Animation, render_camera, render_clock, render_text, render_weather, to_webp
from render.text import theme_from_color
from render.weather import ICONS

SCALE = 8
# Every clock blinks the same way, so the animated sheet only needs a few.
SHEET_CLOCKS = ("clock_09", "clock_22", "clock_12h")

MDNS = ("224.0.0.251", 5353)
SERVICE = "_tuneshine._tcp.local"
PTR, A, TXT, SRV = 12, 1, 16, 33


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


def frames(animate: bool = True) -> dict[str, Image.Image | Animation]:
    now = datetime(2026, 10, 3, 9, 41, tzinfo=UTC)
    result = {
        f"clock_{hour:02d}": render_clock(now.replace(hour=hour), animate=animate)
        for hour in (2, 6, 9, 13, 18, 22)
    }
    result["clock_12h"] = render_clock(now.replace(hour=21), use_24h=False, animate=animate)
    result["clock_wednesday"] = render_clock(now.replace(day=7, hour=15), animate=animate)
    result["clock_no_date"] = render_clock(now, show_date=False, animate=animate)
    camera = sample_camera()
    result["camera"] = render_camera(camera, label="Front door", animate=animate)
    result["camera_long_name"] = render_camera(
        camera, label="Back garden doorbell", animate=animate
    )
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
        result[f"weather_{condition}"] = render_weather(
            condition, temp, high=high, low=low, animate=animate
        )
    return result


def contact_sheet(pages: list[Image.Image], columns: int = 6, scale: int = 4) -> Image.Image:
    tile = 64 * scale + 8
    rows = -(-len(pages) // columns)
    sheet = Image.new("RGB", (columns * tile, rows * tile), (30, 30, 30))
    for index, image in enumerate(pages):
        thumb = image.resize((64 * scale, 64 * scale), Image.Resampling.NEAREST)
        sheet.paste(thumb, ((index % columns) * tile + 4, (index // columns) * tile + 4))
    return sheet


def animated_sheet(pages: list[Animation], path: Path, columns: int = 7, scale: int = 3) -> None:
    """Play every animation side by side, each on its own loop, at the device's frame rate."""
    tick = min(page.duration for page in pages)
    ticks = max(len(page.frames) * page.duration for page in pages) // tick
    sheets = [
        contact_sheet(
            [page.frames[(i * tick // page.duration) % len(page.frames)] for page in pages],
            columns,
            scale,
        )
        for i in range(ticks)
    ]
    sheets[0].save(
        path,
        save_all=True,
        append_images=sheets[1:],
        duration=tick,
        loop=0,
        quality=75,
        method=4,
    )


def led(image: Image.Image) -> Image.Image:
    """Upscale with a dark gap between pixels, roughly how the matrix looks."""
    big = image.resize((64 * SCALE, 64 * SCALE), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(big)
    for i in range(0, 64 * SCALE, SCALE):
        draw.line((i, 0, i, 64 * SCALE), fill=(12, 12, 12))
        draw.line((0, i, 64 * SCALE, i), fill=(12, 12, 12))
    return big


def _query(name: str, qtype: int) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode() for part in name.split("."))
    return struct.pack("!6H", 0, 0, 1, 0, 0, 0) + labels + b"\0" + struct.pack("!2H", qtype, 1)


def _name(data: bytes, offset: int) -> tuple[str, int]:
    """Read a possibly compressed DNS name; return it and the offset just after it."""
    labels: list[str] = []
    end = None
    for _ in range(128):
        length = data[offset]
        if length & 0xC0 == 0xC0:
            end = end or offset + 2
            offset = (length & 0x3F) << 8 | data[offset + 1]
        elif length:
            labels.append(data[offset + 1 : offset + 1 + length].decode(errors="replace"))
            offset += 1 + length
        else:
            return ".".join(labels), end or offset + 1
    raise ValueError("DNS name loops")


def _records(data: bytes):
    """Yield (name, type, rdata offset, rdata length) for every record in a DNS packet."""
    _, _, questions, *sections = struct.unpack_from("!6H", data)
    offset = 12
    for _ in range(questions):
        offset = _name(data, offset)[1] + 4
    for _ in range(sum(sections)):
        name, offset = _name(data, offset)
        rtype, _, _, length = struct.unpack_from("!HHIH", data, offset)
        yield name.lower(), rtype, offset + 10, length
        offset += 10 + length


def discover(timeout: float = 2.0) -> list[tuple[str, str]]:
    """Ask the LAN for Tuneshines over mDNS; return (name, address) pairs."""
    instances: dict[str, str] = {}
    targets: dict[str, str] = {}
    addresses: dict[str, str] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.settimeout(0.2)
        sock.sendto(_query(SERVICE, PTR), MDNS)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = sock.recv(9000)
            except TimeoutError:
                continue
            try:
                for name, rtype, rdata, length in _records(data):
                    if rtype == PTR and name == SERVICE.lower():
                        instance = _name(data, rdata)[0].lower()
                        instances.setdefault(instance, instance.split(".")[0])
                    elif rtype == SRV:
                        targets[name] = _name(data, rdata + 6)[0].lower()
                    elif rtype == A:
                        addresses[name] = socket.inet_ntoa(data[rdata : rdata + 4])
                    elif rtype == TXT:
                        end, i = rdata + length, rdata
                        while i < end:
                            key, _, value = data[i + 1 : i + 1 + data[i]].partition(b"=")
                            if key == b"deviceName" and value:
                                instances[name] = value.decode(errors="replace")
                            i += 1 + data[i]
            except (IndexError, struct.error, ValueError):
                continue
    found = []
    for instance, label in instances.items():
        target = targets.get(instance)
        address = addresses.get(target) if target else None
        if target and not address:
            try:
                address = socket.gethostbyname(target)
            except OSError:
                pass
        if address:
            found.append((label, address))
    return found


def find_host() -> str:
    devices = discover()
    if not devices:
        sys.exit("No Tuneshine found on the network; pass its address with --push HOST")
    if len(devices) > 1:
        listing = "\n".join(f"  {address}  {name}" for name, address in devices)
        sys.exit(f"Found more than one Tuneshine; pick one with --push HOST:\n{listing}")
    name, address = devices[0]
    print(f"found {name} at {address}")
    return address


def push(host: str, name: str, image: Image.Image | Animation) -> None:
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
    parser.add_argument(
        "--push",
        nargs="?",
        const="",
        metavar="HOST",
        help="send each frame to a Tuneshine (found over mDNS if HOST is left out)",
    )
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between pushed frames")
    parser.add_argument("--still", action="store_true", help="render pages without animation")
    args = parser.parse_args()
    host = (args.push or find_host()) if args.push is not None else None

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rendered = frames(animate=not args.still)

    for name, page in rendered.items():
        image = page.frames[0] if isinstance(page, Animation) else page
        assert image.size == (64, 64), name
        webp = to_webp(page)
        image.save(out / f"{name}.png")
        led(image).save(out / f"{name}@8x.png")
        if isinstance(page, Animation):
            (out / f"{name}.webp").write_bytes(webp)
            big = [led(frame) for frame in page.frames]
            big[0].save(
                out / f"{name}@8x.gif",
                save_all=True,
                append_images=big[1:],
                duration=page.duration,
                loop=0,
            )
            print(f"{name}: {len(webp)} bytes webp, {len(page.frames)} frames")
        else:
            print(f"{name}: {len(webp)} bytes webp")

    still = rendered if args.still else frames(animate=False)
    contact_sheet(list(still.values())).save(out / "contact_sheet.png")
    animations = [
        page
        for name, page in rendered.items()
        if isinstance(page, Animation) and (not name.startswith("clock") or name in SHEET_CLOCKS)
    ]
    if animations:
        animated_sheet(animations, out / "contact_sheet.webp")
    print(f"wrote {len(rendered)} pages to {out}/")

    if host:
        for name, image in rendered.items():
            push(host, name, image)
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
