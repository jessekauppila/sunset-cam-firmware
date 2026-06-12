"""Report the device's confirmed sun-tap aim to the cloud so it flips the
camera to 'ready'. Auth mirrors heartbeat.py / upload.py."""
from __future__ import annotations

from typing import Callable

import requests


def post_placement(
    config: dict, placement: dict, poster: Callable = requests.post, timeout_s: float = 10.0
) -> dict:
    url = f"{config['api_base'].rstrip('/')}/api/cameras/{config['camera_id']}/placement"
    headers = {
        "Authorization": f"Bearer {config['device_token']}",
        "Content-Type": "application/json",
    }
    resp = poster(
        url,
        json={"azimuth_deg": placement["azimuth_deg"], "tilt_deg": placement["tilt_deg"]},
        headers=headers,
        timeout=timeout_s,
    )
    resp.raise_for_status()
    return resp.json()
