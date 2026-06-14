"""Device registration handshake: announce identity + firmware/capabilities to
the cloud and learn placement_status. Keyed by claim_code+hardware_id (no Bearer).
Register does NOT return a device token — provisioning baked it into config.json."""
from __future__ import annotations

from typing import Callable

import requests


def post_register(
    config: dict, poster: Callable = requests.post, timeout_s: float = 10.0
) -> dict:
    url = f"{config['api_base'].rstrip('/')}/api/cameras/register"
    body = {
        "claim_code": config["claim_code"],
        "hardware_id": config["hardware_id"],
        "capabilities": config.get("capabilities", {}),
        "firmware_version": config.get("firmware_version"),
    }
    resp = poster(url, json=body, headers={"Content-Type": "application/json"}, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    return {
        "camera_id": data.get("camera_id"),
        "placement_status": data.get("placement_status"),
        "placement": data.get("placement"),
    }
