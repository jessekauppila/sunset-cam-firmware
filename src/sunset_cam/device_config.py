"""Merge the cloud-delivered location into the device config so the aiming
server (run-setup-server.py, config-driven) can read lat/lng."""
from __future__ import annotations

import json
from pathlib import Path


def write_location(config_path: str, lat: float, lng: float) -> None:
    p = Path(config_path)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    cfg["lat"] = lat
    cfg["lng"] = lng
    p.write_text(json.dumps(cfg, indent=2) + "\n")
