#!/usr/bin/env python3
"""Run the captive-portal WiFi-onboarding Flask app on real Pi hardware.

Scans for nearby networks via NetworkManager (``nmcli``), then serves the portal
on port 80 so iOS/Android captive-portal detection pops the browser when the Pi
is in AP / hotspot mode.

Example (run as root so port 80 is bindable):
  sudo /opt/sunset-cam/.venv/bin/python /opt/sunset-cam/scripts/run-setup-app.py

The Pi must already be in AP / hotspot mode before running this.
"""
from __future__ import annotations

from sunset_cam.setup_app import create_app
from sunset_cam.wifi_scan import scan_networks
from sunset_cam.wifi_setup import WifiSetupService

PORT = 80
HOST = "0.0.0.0"


def main() -> None:
    wifi_service = WifiSetupService()
    app = create_app(scan_fn=scan_networks, wifi_service=wifi_service)
    print(f"[setup-app] Captive portal on {HOST}:{PORT} — "
          f"connect to the Pi AP then open any browser page.")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
