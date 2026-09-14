#!/usr/bin/env python3
"""System-level RetroPie recorder using FFmpeg KMS/framebuffer capture."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import pwd


CONFIG_PATH = Path("/etc/rprec-software.json")
STATE_PATH = Path("/dev/shm/rprec-software-state.json")
CONTEXT_PATH = Path("/dev/shm/rprec-game-context.json")


def unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ffmpeg_text(option: str) -> str:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", option], capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    return result.stdout + result.stderr


def choose_backend(config: dict) -> str:
    requested = str(config.get("backend", "auto"))
    if requested != "auto":
        return requested
    formats = ffmpeg_text("-formats")
    if "kmsgrab" in formats and Path(config.get("drm_device", "/dev/dri/card0")).exists():
        return "kmsgrab"
    if "fbdev" in formats and Path(config.get("framebuffer_device", "/dev/fb0")).exists():
        return "fbdev"
    if "x11grab" in formats and os.environ.get("DISPLAY"):
        return "x11grab"
    raise RuntimeError("FFmpeg exposes no usable kmsgrab, fbdev, or x11grab input")


def choose_encoder(config: dict) -> str:
    requested = str(config.get("encoder", "auto"))
    if requested != "auto":
        return requested
    encoders = ffmpeg_text("-encoders")
    for name in ("h264_v4l2m2m", "h264_omx", "libx264"):
        if re.search(rf"\b{re.escape(name)}\b", encoders):
            return name
    raise RuntimeError("FFmpeg exposes no supported H.264 encoder")


def safe_name(value: str, fallback: str) -> str:
    value = Path(value).stem if value else fallback
    value = re.sub(r"[^A-Za-z0-9._()\[\] +'-]", "_", value).strip(" .")
    return value[:120] or fallback


def build_command(config: dict, output: Path) -> tuple[list[str], str, str]:
    backend = choose_backend(config)
    encoder = choose_encoder(config)
    fps = str(int(config.get("framerate", 30)))
    width = int(config.get("output_width", 1280))
    if backend == "dispmanx":
        return ([
            "/usr/bin/python3", "/usr/local/lib/rprec/rprec-session.py",
            "--config", str(CONFIG_PATH), "--output", str(output),
        ], backend, encoder)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]

    if backend == "kmsgrab":
        command += [
            "-f", "kmsgrab", "-device", str(config.get("drm_device", "/dev/dri/card0")),
            "-framerate", fps, "-i", "-",
            "-vf", f"hwdownload,format=bgr0,scale={width}:-2:flags=fast_bilinear,format=yuv420p",
        ]
    elif backend == "fbdev":
        command += [
            "-framerate", fps, "-f", "fbdev", "-i",
            str(config.get("framebuffer_device", "/dev/fb0")),
            "-vf", f"scale={width}:-2:flags=fast_bilinear,format=yuv420p",
        ]
    elif backend == "x11grab":
        command += [
            "-framerate", fps, "-f", "x11grab", "-i",
            str(config.get("x11_display", ":0.0")),
            "-vf", f"scale={width}:-2:flags=fast_bilinear,format=yuv420p",
        ]
    else:
        raise RuntimeError(f"Unknown backend: {backend}")

    audio = str(config.get("audio_capture_device", "")).strip()
    if audio:
        command += ["-thread_queue_size", "2048", "-f", "alsa", "-i", audio]

    command += ["-map", "0:v:0", "-c:v", encoder]
    if encoder == "libx264":
        command += ["-preset", "ultrafast", "-crf", "20"]
    else:
        command += ["-b:v", str(config.get("video_bitrate", "6000k"))]
    if audio:
        command += [
            "-map", "1:a:0", "-c:a", "aac", "-b:a",
            str(config.get("audio_bitrate", "160k")),
            "-af", "aresample=async=1:first_pts=0",
        ]
    command += [str(output)]
    return command, backend, encoder


def read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def give_to_recording_user(path: Path, state=None) -> None:
    state = state or {}
    uid = int(state.get("owner_uid", os.environ.get("SUDO_UID", os.getuid())))
    gid = int(state.get("owner_gid", os.environ.get("SUDO_GID", os.getgid())))
    try:
        os.chown(str(path), uid, gid)
    except (FileNotFoundError, PermissionError):
        pass


def recording_owner(config: dict) -> tuple[int, int]:
    if "SUDO_UID" in os.environ:
        return int(os.environ["SUDO_UID"]), int(os.environ.get("SUDO_GID", 0))
    account = pwd.getpwnam(str(config.get("recording_user", "pi")))
    return account.pw_uid, account.pw_gid


def show_notification(config: dict, message: str) -> None:
    if not config.get("notifications", True):
        return
    port = int(config.get("retroarch_command_port", 55355))
    payload = f"SHOW_MSG {message}".encode("utf-8", "replace")[:1000]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.sendto(payload, ("127.0.0.1", port))
    except OSError:
        pass


def start_recording(config: dict, system: str, emulator: str, rom: str,
                    apply_launch_delay: bool = True) -> int:
    state = read_state()
    old_pid = int(state.get("pid", 0))
    if old_pid and process_alive(old_pid):
        print(f"Already recording with PID {old_pid}: {state.get('file', '')}")
        return 1

    delay = (max(0, float(config.get("launch_delay_seconds", 0)))
             if apply_launch_delay else 0)
    if delay:
        time.sleep(delay)
    output_root = Path(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    owner_uid, owner_gid = recording_owner(config)
    owner = {"owner_uid": owner_uid, "owner_gid": owner_gid}
    give_to_recording_user(output_root, owner)
    minimum = float(config.get("minimum_free_gib", 2))
    free_gib = shutil.disk_usage(output_root).free / (1024 ** 3)
    if free_gib < minimum:
        print(f"Refusing to record: only {free_gib:.1f} GiB free", file=sys.stderr)
        return 1

    folder = output_root / safe_name(system, "unknown-system")
    folder.mkdir(parents=True, exist_ok=True)
    give_to_recording_user(folder, owner)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output = folder / f"{safe_name(rom, 'unknown-game')}_{stamp}.mkv"
    log_path = output.with_suffix(".ffmpeg.log")
    command, backend, encoder = build_command(config, output)
    log = log_path.open("w", encoding="utf-8")
    give_to_recording_user(log_path)
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
        start_new_session=True,
    )
    state = {
        "pid": process.pid, "file": str(output), "log": str(log_path),
        "backend": backend, "encoder": encoder, "system": system,
        "emulator": emulator, "rom": rom, "started": time.time(),
        "owner_uid": owner_uid, "owner_gid": owner_gid,
    }
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    time.sleep(1)
    if process.poll() is not None:
        log.close()
        print(f"FFmpeg failed with code {process.returncode}; inspect {log_path}", file=sys.stderr)
        unlink_if_present(STATE_PATH)
        show_notification(config, "[REC] Recording failed")
        return 1
    log.close()
    show_notification(config, "[REC] Recording started")
    print(f"Recording {output} with {backend}/{encoder} (PID {process.pid})")
    return 0


def stop_recording(config: dict) -> int:
    state = read_state()
    pid = int(state.get("pid", 0))
    if not pid or not process_alive(pid):
        unlink_if_present(STATE_PATH)
        print("Not recording")
        return 1
    # Signal only the session supervisor. It stops the grabber first, then lets
    # FFmpeg drain queued frames and finalize the container cleanly.
    os.kill(pid, signal.SIGTERM)
    for _ in range(450):
        if not process_alive(pid):
            break
        time.sleep(0.1)
    else:
        os.killpg(pid, signal.SIGTERM)
    for value in (state.get("file"), state.get("log")):
        if value:
            give_to_recording_user(Path(value), state)
    unlink_if_present(STATE_PATH)
    show_notification(config, "[REC] Recording stopped")
    print(f"Finalized {state.get('file', '')}")
    return 0


def show_status(config: dict) -> int:
    state = read_state()
    pid = int(state.get("pid", 0))
    state["recording"] = bool(pid and process_alive(pid))
    state["game"] = read_context()
    state["controller"] = {
        "enabled": bool(config.get("controller_enabled", False)),
        "device": str(config.get("controller_device_name", "")),
        "combo": config.get("controller_combo", []),
        "hold_seconds": float(config.get("controller_hold_seconds", 0.8)),
    }
    try:
        state["detected_backend"] = choose_backend(config)
        state["detected_encoder"] = choose_encoder(config)
    except Exception as exc:
        state["detection_error"] = str(exc)
    print(json.dumps(state, indent=2))
    return 0


def read_context() -> dict:
    try:
        return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def game_start(config: dict, system: str, emulator: str, rom: str) -> int:
    context = {
        "system": system, "emulator": emulator, "rom": rom,
        "started": time.time(),
    }
    temporary = CONTEXT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(context, indent=2), encoding="utf-8")
    temporary.replace(CONTEXT_PATH)
    if config.get("auto_record", False):
        return start_recording(config, system, emulator, rom)
    return 0


def game_end(config: dict) -> int:
    state = read_state()
    pid = int(state.get("pid", 0))
    result = stop_recording(config) if pid and process_alive(pid) else 0
    unlink_if_present(CONTEXT_PATH)
    return result


def toggle_recording(config: dict) -> int:
    state = read_state()
    pid = int(state.get("pid", 0))
    if pid and process_alive(pid):
        return stop_recording(config)
    context = read_context()
    if not context and config.get("controller_in_game_only", True):
        print("No game is currently running", file=sys.stderr)
        return 1
    return start_recording(
        config,
        str(context.get("system", "manual")),
        str(context.get("emulator", "manual")),
        str(context.get("rom", "Controller Recording")),
        apply_launch_delay=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start")
    start.add_argument("system", nargs="?", default="manual")
    start.add_argument("emulator", nargs="?", default="manual")
    start.add_argument("rom", nargs="?", default="manual-recording")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("probe")
    sub.add_parser("toggle")
    game_begin = sub.add_parser("game-start")
    game_begin.add_argument("system", nargs="?", default="unknown")
    game_begin.add_argument("emulator", nargs="?", default="unknown")
    game_begin.add_argument("rom", nargs="?", default="unknown")
    sub.add_parser("game-end")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.action == "start":
        return start_recording(config, args.system, args.emulator, args.rom)
    if args.action == "stop":
        return stop_recording(config)
    if args.action == "toggle":
        return toggle_recording(config)
    if args.action == "game-start":
        return game_start(config, args.system, args.emulator, args.rom)
    if args.action == "game-end":
        return game_end(config)
    return show_status(config)


if __name__ == "__main__":
    raise SystemExit(main())
