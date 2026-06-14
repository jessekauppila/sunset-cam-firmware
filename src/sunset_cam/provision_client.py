"""Provisioning mint client: call the cloud /api/cameras/provision endpoint to
create a camera identity row and obtain a permanent claim_code + device_token.
Auth is via CRON_SECRET Bearer token (operator-level, not per-device)."""
from __future__ import annotations

from typing import Callable

import requests


def provision_unit(
    api_base: str,
    cron_secret: str,
    hardware_id: str,
    label: str | None = None,
    poster: Callable = requests.post,
    timeout_s: float = 15.0,
) -> dict:
    """POST /api/cameras/provision with Bearer cron_secret.

    Returns a dict with exactly 3 fields: {camera_id, claim_code, device_token}.
    Raises on HTTP errors (raise_for_status called before json()).
    """
    url = f"{api_base.rstrip('/')}/api/cameras/provision"
    headers = {
        "Authorization": f"Bearer {cron_secret}",
        "Content-Type": "application/json",
    }
    body = {
        "hardware_id": hardware_id,
        "label": label,
    }
    resp = poster(url, json=body, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    return {
        "camera_id": data["camera_id"],
        "claim_code": data["claim_code"],
        "device_token": data["device_token"],
    }
