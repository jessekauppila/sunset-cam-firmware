"""Device heartbeat: report liveness and read placement status from the cloud.
Auth mirrors upload.py — Bearer device_token to {api_base}/api/cameras/{camera_id}/heartbeat."""
from __future__ import annotations

from typing import Callable

import requests


def _coord(v):
    """Coerce a lat/lng to float; the cloud serializes them as JSON strings."""
    return float(v) if v is not None else None


def parse_placement(body: dict) -> dict:
    """Extract supervisor-relevant placement from a heartbeat response. Handles
    both the awaiting_aim shape (top-level lat/lng) and the ready shape (nested
    under body['placement'] with the full aim + provenance)."""
    placement = body.get("placement") or {}
    return {
        "placement_status": body.get("placement_status"),
        "lat": _coord(placement.get("lat", body.get("lat"))),
        "lng": _coord(placement.get("lng", body.get("lng"))),
        "azimuth_deg": placement.get("azimuth_deg"),
        "tilt_deg": placement.get("tilt_deg"),
        "coarse": placement.get("coarse"),
        "azimuth_source": placement.get("azimuth_source"),
        "bracket": placement.get("bracket"),
        "phase_preference": placement.get("phase_preference"),
    }


def parse_directives(body: dict) -> list:
    """Pending control-plane directives the cloud handed back in a heartbeat
    response (empty when absent). Each is a dict with at least id + type."""
    return body.get("directives") or []


def post_heartbeat(
    config: dict, poster: Callable = requests.post, timeout_s: float = 10.0,
    results: list | None = None,
) -> dict:
    url = f"{config['api_base'].rstrip('/')}/api/cameras/{config['camera_id']}/heartbeat"
    headers = {
        "Authorization": f"Bearer {config['device_token']}",
        "Content-Type": "application/json",
    }
    body = {"request_placement": True}
    if results:
        body["directive_results"] = results   # report executed control-plane directives
    resp = poster(url, json=body, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    response_body = resp.json()
    return {**parse_placement(response_body), "directives": parse_directives(response_body)}
