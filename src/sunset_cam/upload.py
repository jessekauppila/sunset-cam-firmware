"""POST a captured JPEG to the parent app's snapshot endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

import requests


class SnapshotAck(TypedDict):
    snapshot_id: int
    accepted_at: str


def upload_snapshot(
    config: dict,
    jpeg_bytes: bytes,
    captured_at: datetime,
    timeout_s: float = 10.0,
) -> SnapshotAck:
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    url = f"{config['api_base'].rstrip('/')}/api/cameras/{config['camera_id']}/snapshot"

    files = {
        "image": ("frame.jpg", jpeg_bytes, "image/jpeg"),
    }
    data = {
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "phase": config["phase"],
        "window_id": config["window_id"],
    }
    headers = {"Authorization": f"Bearer {config['device_token']}"}

    response = requests.post(
        url, data=data, files=files, headers=headers, timeout=timeout_s
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"snapshot upload failed: HTTP {response.status_code} {response.text}"
        )
    body = response.json()
    return SnapshotAck(
        snapshot_id=int(body["snapshot_id"]),
        accepted_at=str(body["accepted_at"]),
    )
