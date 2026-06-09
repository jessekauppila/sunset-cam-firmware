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

import smbus2

from sunset_cam.aiming_config import resolve_aiming_params
from sunset_cam.capture import capture_jpeg
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

    reader = make_orientation_reader(smbus2.SMBus(1))
    service = AimingService(
        lat=params["lat"], lng=params["lng"], phase=params["phase"],
        hfov_deg=params["hfov"], width=params["width"],
        frame_source=capture_jpeg, reader=reader,
        placement_sink=lambda placement: post_placement(config, placement),
    )
    print(f"setup-server on :{args.port} — open http://<pi>:{args.port}/ from a phone")
    serve(service, args.port)


if __name__ == "__main__":
    main()
