# sunset-cam-firmware

Firmware for the custom Raspberry Pi Zero 2 W edge cameras feeding the
sunrise/sunset map. Tier 0 scope: capture JPEGs at 1 fps inside a
hardcoded UTC capture window and POST them to
`POST /api/cameras/<id>/snapshot` on the parent app.

## Parent project

This repo holds **only code that runs on a camera device** (Pi Zero 2 W
under `picamera2` + systemd). Everything else — the Next.js web app,
the snapshot ingest endpoint, the ML pipeline, the kiosk, the AR
placement portal — lives in
[`the-sunset-webcam-map`](../the-sunset-webcam-map) (path:
`~/GitHub/the-sunset-webcam-map`). The split is a deliberate
decision from 2026-05-03; see that repo's
`docs/device-protocol.md` for the wire spec, and
`docs/superpowers/plans/2026-05-12-tier-0-cameras.md` for the
end-to-end deploy runbook.

The Pi deploy path used in Session 3 was `rsync` from this Mac, but
now that this repo is on GitHub the `git clone` example below works
too.

## Helper scripts

`scripts/configure.sh` and `scripts/snap-now.sh` exist to avoid the
nano + JSON-by-hand + sudo deploy pain from Session 3. Both run from
the dev mac and SSH into the Pi themselves — see the header comments
in each for usage.

## Quickstart on a fresh Pi

1. Flash Raspberry Pi OS Lite (64-bit, headless). Enable SSH + Wi-Fi
   in the imager.
2. SSH in. Then:
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-venv git
   git clone <this repo> /opt/sunset-cam
   cd /opt/sunset-cam
   python3 -m venv --system-site-packages .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/pip install -e .
   ```
   `--system-site-packages` is required so the venv can see the
   apt-installed `picamera2`.
3. Copy `config/config.example.json` to `config/config.json` and fill
   in `camera_id`, `device_token`, `api_base`,
   `capture_window_start_utc`, and `capture_window_end_utc`. Get
   `camera_id` and `device_token` from the parent repo's
   `scripts/tier0-create-camera.sh`.
4. Install and start the systemd unit:
   ```bash
   sudo cp systemd/sunset-cam.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now sunset-cam.service
   journalctl -u sunset-cam -f
   ```

## Local dev (no Pi)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

`tests/` is fully runnable on a Mac. The `capture` module is the only
piece that needs a real Pi — it lazy-imports `picamera2` so the rest of
the package imports cleanly without it.
