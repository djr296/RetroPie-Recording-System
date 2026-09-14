#!/usr/bin/env python3
"""Run one DispmanX-to-FFmpeg recording pipeline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


stopping = False


def request_stop(_signum, _frame):
    global stopping
    stopping = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))

    width = int(config.get("output_width", 1280))
    height = int(config.get("output_height", 720))
    fps = int(config.get("framerate", 30))
    capture_format = str(config.get("capture_format", "yuv420p"))
    if capture_format not in ("yuv420p", "rgb565le"):
        raise ValueError(f"Unsupported capture_format: {capture_format}")
    grabber_command = [
        str(config.get("dispmanx_grabber", "/usr/local/lib/rprec/dispmanx-grab")),
        "--width", str(width), "--height", str(height), "--fps", str(fps),
        "--format", capture_format,
    ]
    ffmpeg_command = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-thread_queue_size", "128", "-f", "rawvideo",
        "-pixel_format", capture_format, "-video_size", f"{width}x{height}",
        "-framerate", str(fps), "-i", "pipe:0",
    ]
    audio = str(config.get("audio_capture_device", "")).strip()
    audio_read_fd = -1
    audio_write_fd = -1
    audio_command = []
    if audio:
        audio_read_fd, audio_write_fd = os.pipe()
        audio_command = [
            "arecord", "-q", "-D", audio, "-t", "raw", "-f", "S16_LE",
            "-c", "2", "-r", "48000",
        ]
        ffmpeg_command += [
            "-thread_queue_size", "2048", "-f", "s16le", "-ac", "2",
            "-ar", "48000", "-i", f"pipe:{audio_read_fd}",
        ]
    ffmpeg_command += [
        "-map", "0:v:0", "-c:v", str(config.get("encoder", "h264_omx")),
        "-b:v", str(config.get("video_bitrate", "6000k")),
    ]
    if audio:
        ffmpeg_command += [
            "-map", "1:a:0", "-c:a", "aac", "-b:a",
            str(config.get("audio_bitrate", "160k")),
            "-af", "aresample=async=1:first_pts=0",
        ]
    ffmpeg_command += [str(args.output)]

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    grabber = subprocess.Popen(grabber_command, stdout=subprocess.PIPE)
    assert grabber.stdout is not None
    audio_capture = None
    if audio:
        audio_capture = subprocess.Popen(audio_command, stdout=audio_write_fd)
        os.close(audio_write_fd)
        audio_write_fd = -1
    encoder = subprocess.Popen(
        ffmpeg_command, stdin=grabber.stdout,
        pass_fds=(audio_read_fd,) if audio else (),
    )
    grabber.stdout.close()
    if audio_read_fd >= 0:
        os.close(audio_read_fd)
        audio_read_fd = -1

    while (not stopping and encoder.poll() is None and grabber.poll() is None
           and (audio_capture is None or audio_capture.poll() is None)):
        time.sleep(0.2)

    # Stop both producers first. Their closed pipes give FFmpeg EOF, allowing it
    # to drain queued audio and video and write the Matroska index before exit.
    producers = [grabber]
    if audio_capture is not None:
        producers.append(audio_capture)
    for process in producers:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    for process in producers:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)

    try:
        encoder.wait(timeout=30)
    except subprocess.TimeoutExpired:
        encoder.send_signal(signal.SIGINT)
        try:
            encoder.wait(timeout=10)
        except subprocess.TimeoutExpired:
            encoder.terminate()
            encoder.wait(timeout=5)
    return 0 if encoder.returncode in (0, 255) else encoder.returncode


if __name__ == "__main__":
    raise SystemExit(main())
