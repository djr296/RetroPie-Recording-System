# RetroPie Recording System

Record RetroPie gameplay directly on a Raspberry Pi 4—video, game audio, and
controller controls included. No capture card or other recording hardware is
required.

The recorder was built for the official Raspberry Pi 4 RetroPie image based on
Raspberry Pi OS Buster with the FKMS video driver. It records the full composed
display at 720p and 30 FPS using the Pi's hardware H.264 encoder. This includes
hardware-rendered libretro cores such as Flycast, which RetroArch's built-in
recorder cannot reliably capture on this setup.

## What you get

- 1280×720, 30 FPS H.264 video
- Clean stereo game audio
- Start and stop recording from the controller
- In-game recording started/stopped notifications
- Automatic folders and filenames based on the launched game
- Automatic finalization if you exit a game while recording
- A free-space safety check
- Fully offline operation after installation

## Install

Download `retropie-recording-system-v0.1.0.zip` from the
[latest release](https://github.com/djr296/RetroPie-Recording-System/releases/latest)
and copy it to `/home/pi` on your RetroPie.

Connect over SSH and run:

```bash
cd /home/pi
unzip retropie-recording-system-v0.1.0.zip -d retropie-recording-system
cd retropie-recording-system
chmod +x install.sh
sudo ./install.sh
sudo rprec-audio-setup
sudo reboot
```

After the Pi restarts, reconnect over SSH and run:

```bash
sudo rprec-controller-setup
```

When prompted, hold **L3 + R3** together and then release them. Other button
combinations work too, but L3 + R3 avoids RetroPie's usual Select hotkeys.

Return to EmulationStation and launch a game. The recorder is ready.

## Record a game

While playing:

1. Hold L3 + R3 for about one second.
2. Wait for `[REC] Recording started` to appear.
3. Play normally.
4. Hold L3 + R3 again.
5. Wait for `[REC] Recording stopped` to appear.

If you leave the game while recording, the video is stopped and saved
automatically.

Recordings are stored here:

```text
/home/pi/RetroPie/recordings-system/<system>/<game>_<date-and-time>.mkv
```

They can be copied to a PC with WinSCP, FileZilla, SCP, or another SFTP tool.

## Check the recorder

```bash
rprec status
```

This shows the current game, controller, recording state, capture backend, and
video encoder.

The controller service can be checked with:

```bash
systemctl status rprec-controller --no-pager
```

## Change the controller shortcut

Run the setup again:

```bash
sudo rprec-controller-setup
```

Hold the new combination when prompted. The service restarts automatically.

## Audio recovery

The audio setup backs up the previous ALSA configuration before changing it.
If HDMI audio stops working or sounds wrong, restore it with:

```bash
sudo rprec-audio-restore
sudo reboot
```

If automatic HDMI detection chooses the wrong output, list the available
devices with `aplay -l`, then run the setup with the desired device:

```bash
sudo RPREC_HDMI_PCM='hw:CARD=YOUR_CARD,DEV=0' rprec-audio-setup
sudo reboot
```

## Uninstall

Restore the original audio configuration first, then remove the recorder:

```bash
sudo rprec-audio-restore
sudo rprec-uninstall
sudo reboot
```

Existing recordings are never deleted by the uninstaller.

## Compatibility

Version 0.1.0 targets:

- Raspberry Pi 4 Model B
- RetroPie on Raspberry Pi OS 10 (Buster)
- Linux 5.10 Raspberry Pi kernel
- Legacy/FKMS graphics (`dtoverlay=vc4-fkms-v3d`)
- HDMI audio through ALSA
- Libretro emulators, including Flycast

Other Raspberry Pi models, KMS-only installations, Bookworm, and standalone
emulators have not yet been validated. The recording popup uses RetroArch's
local command interface, so standalone emulators may record correctly without
showing the popup.

## Privacy

The recorder contains no telemetry, accounts, cloud services, or internet
features. Recordings and configuration stay on the Raspberry Pi.

## License

Released under the MIT License.
