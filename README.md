# sunset-cam-firmware

Firmware for the custom Raspberry Pi Zero 2 W edge cameras feeding the
sunrise/sunset map. Tier 0 scope: capture JPEGs at 1 fps inside a
hardcoded UTC capture window and POST them to
`POST /api/cameras/<id>/snapshot` on the parent app.

See `the-sunset-webcam-map/docs/device-protocol.md` for the wire spec.

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
