"""Send a captured JPEG to a sink: the parent app's snapshot endpoint, or a
Welkin frame ingest. :func:`send_frame` picks by the active profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

import requests

if TYPE_CHECKING:
    from sunset_cam.profiles import Profile


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


def upload_frame(
    url: str,
    camera_id: int | str,
    jpeg_bytes: bytes,
    captured_at: datetime,
    profile: str,
    token: str | None = None,
    timeout_s: float = 10.0,
) -> dict:
    """POST a raw JPEG to a Welkin ingest: ``{url}/frames/{camera_id}``.

    The body is the JPEG itself (not multipart), so a stdlib receiver can
    write it straight to disk. Metadata travels in headers.
    """
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    headers = {
        "Content-Type": "image/jpeg",
        "X-Captured-At": captured_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "X-Profile": profile,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        f"{url.rstrip('/')}/frames/{camera_id}",
        data=jpeg_bytes,
        headers=headers,
        timeout=timeout_s,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"frame upload failed: HTTP {response.status_code} {response.text}")
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def send_frame(config: dict, profile: "Profile", jpeg_bytes: bytes, captured_at: datetime) -> dict:
    """Send one frame to the active profile's sink."""
    sink = profile.sink
    if sink["kind"] == "welkin":
        return upload_frame(
            sink["url"],
            config["camera_id"],
            jpeg_bytes,
            captured_at,
            profile=profile.name,
            token=sink.get("token"),
        )
    if sink["kind"] == "sunset":
        merged = {**config, "phase": sink["phase"], "window_id": sink["window_id"]}
        return dict(upload_snapshot(merged, jpeg_bytes, captured_at))
    raise ValueError(f"unknown sink kind {sink['kind']!r}")
