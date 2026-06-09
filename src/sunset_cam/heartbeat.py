"""Device heartbeat: report liveness and read placement status from the cloud.
Auth mirrors upload.py — Bearer device_token to {api_base}/api/cameras/{camera_id}/heartbeat."""
from __future__ import annotations

from typing import Callable

import requests


def parse_placement(body: dict) -> dict:
    """Extract the supervisor-relevant fields from a heartbeat response."""
    return {
        "placement_status": body.get("placement_status"),
        "lat": body.get("lat"),
        "lng": body.get("lng"),
    }


def post_heartbeat(
    config: dict, poster: Callable = requests.post, timeout_s: float = 10.0
) -> dict:
    url = f"{config['api_base'].rstrip('/')}/api/cameras/{config['camera_id']}/heartbeat"
    headers = {
        "Authorization": f"Bearer {config['device_token']}",
        "Content-Type": "application/json",
    }
    resp = poster(url, json={"request_placement": True}, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    return parse_placement(resp.json())
