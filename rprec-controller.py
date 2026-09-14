#!/usr/bin/env python3
"""Controller chord listener and interactive configuration for RPREC."""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time


CONFIG_PATH = Path("/etc/rprec-software.json")
EV_KEY = 0x01
EVENT = struct.Struct("@llHHi")
RUNNING = True
BUTTON_NAMES = {
    304: "South/A/B", 305: "East/B/A", 307: "North/X/Y", 308: "West/Y/X",
    310: "Left shoulder", 311: "Right shoulder", 312: "Left trigger",
    313: "Right trigger", 314: "Select/Back", 315: "Start",
    316: "Guide/Home", 317: "Left stick", 318: "Right stick",
}


def stop(_signum, _frame):
    global RUNNING
    RUNNING = False


def input_name(fd: int) -> str:
    size = 256
    request = 0x80000000 | (size << 16) | (ord("E") << 8) | 0x06
    buffer = bytearray(size)
    try:
        fcntl.ioctl(fd, request, buffer)
        return bytes(buffer).split(b"\0", 1)[0].decode("utf-8", "replace")
    except OSError:
        return "Unknown input device"


def open_inputs(name_filter: str = "") -> dict[int, dict]:
    devices = {}
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        name = input_name(fd)
        if name_filter and name_filter.casefold() not in name.casefold():
            os.close(fd)
            continue
        devices[fd] = {
            "path": path, "name": name, "buffer": bytearray(),
            "pressed": set(), "hold_since": None, "triggered": False,
        }
    return devices


def read_events(fd: int, device: dict):
    while True:
        try:
            chunk = os.read(fd, EVENT.size * 64)
        except BlockingIOError:
            break
        if not chunk:
            raise OSError("input device disconnected")
        device["buffer"].extend(chunk)
    complete = len(device["buffer"]) // EVENT.size * EVENT.size
    data = device["buffer"][:complete]
    del device["buffer"][:complete]
    for offset in range(0, len(data), EVENT.size):
        _sec, _usec, event_type, code, value = EVENT.unpack_from(data, offset)
        yield event_type, code, value


def write_config(config: dict) -> None:
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(CONFIG_PATH)


def learn_combo() -> int:
    if os.geteuid() != 0:
        print("Run this setup with sudo.", file=sys.stderr)
        return 1
    devices = open_inputs()
    if not devices:
        print("No readable /dev/input/event devices were found.", file=sys.stderr)
        return 1
    poller = select.poll()
    for fd in devices:
        poller.register(fd, select.POLLIN | select.POLLERR | select.POLLHUP)
    print("Press and hold your desired recording button chord now, then release it.")
    print("L3 + R3 is recommended because it avoids RetroPie's Select hotkeys.")
    chosen_fd = None
    chosen_codes = []
    held = set()
    started = None
    released_at = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        for fd, flags in poller.poll(100):
            if flags & (select.POLLERR | select.POLLHUP):
                continue
            try:
                events = read_events(fd, devices[fd])
                for event_type, code, value in events:
                    if event_type != EV_KEY or value == 2:
                        continue
                    if chosen_fd is None and value == 1:
                        chosen_fd = fd
                        started = time.monotonic()
                        print(f"Controller: {devices[fd]['name']}")
                    if fd != chosen_fd:
                        continue
                    if value == 1:
                        held.add(code)
                        released_at = None
                        if code not in chosen_codes:
                            chosen_codes.append(code)
                            print(f"  {BUTTON_NAMES.get(code, 'Button')} (code {code})")
                    elif value == 0:
                        held.discard(code)
                        if not held:
                            released_at = time.monotonic()
            except OSError:
                continue
        if (started is not None and released_at is not None
                and len(chosen_codes) >= 2
                and time.monotonic() - released_at >= 0.5):
            break
    for fd in devices:
        os.close(fd)
    if chosen_fd is None or len(chosen_codes) < 2:
        print("No multi-button chord was detected. Configuration was unchanged.", file=sys.stderr)
        return 1
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["controller_enabled"] = True
    config["controller_device_name"] = devices[chosen_fd]["name"]
    config["controller_combo"] = chosen_codes
    config.setdefault("controller_hold_seconds", 0.8)
    config.setdefault("controller_in_game_only", True)
    write_config(config)
    subprocess.run(["systemctl", "restart", "rprec-controller.service"], check=False)
    labels = ", ".join(BUTTON_NAMES.get(code, str(code)) for code in chosen_codes)
    print(f"Saved recording chord: {labels}")
    print("The controller recording service has been restarted.")
    return 0


def run_daemon() -> int:
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not config.get("controller_enabled", False):
        print("Controller recording is disabled; run rprec-controller-setup.", flush=True)
        while RUNNING:
            time.sleep(5)
        return 0
    combo = {int(code) for code in config.get("controller_combo", [])}
    if len(combo) < 2:
        print("controller_combo must contain at least two button codes", file=sys.stderr)
        return 1
    hold_seconds = max(0.2, float(config.get("controller_hold_seconds", 0.8)))
    name_filter = str(config.get("controller_device_name", ""))
    devices = {}
    last_scan = 0.0
    while RUNNING:
        now = time.monotonic()
        if now - last_scan >= 2.0:
            known_paths = {device["path"] for device in devices.values()}
            for fd, device in open_inputs(name_filter).items():
                if device["path"] in known_paths:
                    os.close(fd)
                else:
                    devices[fd] = device
                    print(f"Listening to {device['path']}: {device['name']}", flush=True)
            last_scan = now
        readable, _, exceptional = select.select(list(devices), [], list(devices), 0.1)
        for fd in exceptional:
            os.close(fd)
            devices.pop(fd, None)
        for fd in readable:
            device = devices.get(fd)
            if device is None:
                continue
            try:
                for event_type, code, value in read_events(fd, device):
                    if event_type != EV_KEY or code not in combo:
                        continue
                    if value == 1:
                        device["pressed"].add(code)
                    elif value == 0:
                        device["pressed"].discard(code)
            except OSError:
                os.close(fd)
                devices.pop(fd, None)
        now = time.monotonic()
        for device in devices.values():
            if combo.issubset(device["pressed"]):
                if device["hold_since"] is None:
                    device["hold_since"] = now
                elif (not device["triggered"]
                      and now - device["hold_since"] >= hold_seconds):
                    result = subprocess.run(
                        ["/usr/local/bin/rprec", "toggle"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True,
                    )
                    print(result.stdout.strip(), flush=True)
                    device["triggered"] = True
            else:
                device["hold_since"] = None
                device["triggered"] = False
    for fd in devices:
        os.close(fd)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learn", action="store_true")
    args = parser.parse_args()
    return learn_combo() if args.learn else run_daemon()


if __name__ == "__main__":
    raise SystemExit(main())
