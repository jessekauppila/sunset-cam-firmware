#!/usr/bin/env python3
"""Run the captive-portal WiFi-onboarding Flask app on real Pi hardware.

Scans for nearby networks via ``iwlist wlan0 scan``, then serves the portal on
port 80 so that iOS/Android captive-portal detection pops the browser automatically
when the Pi is in AP mode.

Example (run as root so port 80 is bindable):
  sudo /opt/sunset-cam/.venv/bin/python /opt/sunset-cam/scripts/run-setup-app.py

The Pi must already be configured as a hostapd access point before running this.
"""
from __future__ import annotations

import subprocess
import sys

from sunset_cam.setup_app import create_app
from sunset_cam.wifi_scan import parse_iwlist
from sunset_cam.wifi_setup import WifiSetupService

WPA_PATH = "/etc/wpa_supplicant/wpa_supplicant.conf"
IFACE = "wlan0"
PORT = 80
HOST = "0.0.0.0"


def _do_scan() -> list[dict]:
    """Run ``iwlist wlan0 scan`` and return parsed networks.

    Returns an empty list on any subprocess error so the page still renders.
    """
    try:
        result = subprocess.run(
            ["iwlist", IFACE, "scan"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return parse_iwlist(result.stdout)
    except Exception as exc:
        print(f"[setup-app] iwlist scan failed: {exc}", file=sys.stderr)
        return []


def main() -> None:
    wifi_service = WifiSetupService(WPA_PATH)
    app = create_app(scan_fn=_do_scan, wifi_service=wifi_service)
    print(f"[setup-app] Captive portal on {HOST}:{PORT} — "
          f"connect to the Pi AP then open any browser page.")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
