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


def write_identity(
    config_path: str,
    *,
    claim_code: str,
    camera_id: int,
    device_token: str,
    api_base: str,
    hardware_id: str,
) -> None:
    """Write the minimal identity config the device boots with, merge-preserving
    any existing keys (like write_location does). hardware_id MUST be the same id
    provisioning registered the camera under — the device's register client sends
    config['hardware_id'] and the cloud rejects a mismatch (409)."""
    p = Path(config_path)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    cfg["claim_code"] = claim_code
    cfg["camera_id"] = camera_id
    cfg["device_token"] = device_token
    cfg["api_base"] = api_base
    cfg["hardware_id"] = hardware_id
    p.write_text(json.dumps(cfg, indent=2) + "\n")
