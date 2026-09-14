# RetroPie Recording System v0.1.0

RetroPie Recording System records gameplay directly on a Raspberry Pi 4 without
a capture card. This first release captures hardware-rendered games such as
Dreamcast through DispmanX, records clean HDMI game audio, and produces standard
H.264/AAC MKV files that can be copied directly to a PC.

## Highlights

- 720p at 30 FPS using Raspberry Pi hardware encoding
- Clean 48 kHz stereo game audio
- Controller-controlled recording with a configurable button combination
- In-game start and stop notifications
- Automatic game names and per-system recording folders
- Safe finalization when recording stops or a game exits
- Audio restore and complete uninstall commands
- No accounts, telemetry, cloud connection, or additional hardware

## Install

Download `retropie-recording-system-v0.1.0.zip`, copy it to `/home/pi`, and
follow the short instructions in the README.

This release is tested on a Raspberry Pi 4 Model B running RetroPie on Raspberry
Pi OS Buster, Linux 5.10, and the FKMS graphics driver. Other operating system
and graphics configurations are not yet validated.
