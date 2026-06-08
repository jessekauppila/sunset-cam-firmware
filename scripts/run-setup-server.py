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

import smbus2

from sunset_cam.capture import capture_jpeg
from sunset_cam.gyro_driver import make_orientation_reader
from sunset_cam.setup_server import AimingService, serve


def main() -> None:
    ap = argparse.ArgumentParser(description="v0.4 sun-tap aiming setup-server")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lng", type=float, required=True)
    ap.add_argument("--phase", default="sunset", choices=["sunset", "sunrise"])
    ap.add_argument("--hfov", type=float, default=102.0, help="camera horizontal FOV (deg)")
    ap.add_argument("--width", type=int, default=1920, help="capture frame width (px)")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    reader = make_orientation_reader(smbus2.SMBus(1))  # wakes the MPU-6050
    service = AimingService(
        lat=args.lat, lng=args.lng, phase=args.phase,
        hfov_deg=args.hfov, width=args.width,
        frame_source=capture_jpeg, reader=reader,
    )
    print(f"setup-server on :{args.port} — open http://<pi>:{args.port}/ from a phone")
    serve(service, args.port)


if __name__ == "__main__":
    main()
