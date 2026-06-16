#!/usr/bin/env python3
"""Run the v0.4 sun-tap aiming setup-server on real Pi hardware.

Wires the real camera (capture_jpeg) and the woken MPU-6050 reader into the
AimingService, then serves it. Stop the capture service first so the camera
isn't held: `sudo systemctl stop sunset-cam`.

Example:
  sudo /opt/sunset-cam/.venv/bin/python /opt/sunset-cam/scripts/run-setup-server.py \
      --lat 48.7519 --lng -122.4787 --phase sunset --hfov 102 --width 1920
Then open http://<pi-hostname>:8080/ on a phone on the same WiFi.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunset_cam.aiming_config import resolve_aiming_params
from sunset_cam.capture import capture_jpeg, capture_gray_array
from sunset_cam.gyro_driver import make_orientation_reader
from sunset_cam.placement_report import post_placement
from sunset_cam.setup_server import AimingService, serve


def main() -> None:
    ap = argparse.ArgumentParser(description="v0.4 sun-tap aiming setup-server")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lng", type=float, default=None)
    ap.add_argument("--phase", default=None, choices=["sunset", "sunrise", None])
    ap.add_argument("--hfov", type=float, default=None)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--config", default="/opt/sunset-cam/config/config.json")
    args = ap.parse_args()

    config = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        config = json.loads(cfg_path.read_text())
    params = resolve_aiming_params(
        cli={"lat": args.lat, "lng": args.lng, "phase": args.phase,
             "hfov": args.hfov, "width": args.width},
        config=config,
    )

    try:
        import smbus2  # lazy: present only on the Pi; keeps this module importable off-Pi
        reader = make_orientation_reader(smbus2.SMBus(1))
    except Exception:
        reader = None   # MPU optional / no smbus2 off-Pi -> assume mounted level, skip the gate
    # serve the setup-wizard bundle at "/" when it's deployed; else fall back to the
    # legacy single-page render.
    web_dir = Path(__file__).resolve().parent.parent / "web" / "setup-wizard"
    static_dir = str(web_dir) if (web_dir / "index.html").exists() else None
    service = AimingService(
        lat=params["lat"], lng=params["lng"], phase=params["phase"],
        hfov_deg=params["hfov"], width=params["width"],
        mount_roll_ref_deg=params["mount_roll_ref"],
        mount_pitch_ref_deg=params["mount_pitch_ref"],
        level_tol_deg=params["level_tol"],
        frame_source=capture_jpeg, reader=reader,
        sun_source=capture_gray_array,
        placement_sink=lambda placement: post_placement(config, placement),
        static_dir=static_dir,
    )
    print(f"setup-server on :{args.port} ({'wizard' if static_dir else 'legacy page'})"
          f" — open http://<pi>:{args.port}/ from a phone")
    serve(service, args.port)


if __name__ == "__main__":
    main()
