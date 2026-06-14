"""Load and validate the firmware config.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class ConfigError(ValueError):
    """Raised when config.json is missing or invalid."""


class Config(TypedDict):
    camera_id: int
    device_token: str
    api_base: str
    phase: str  # 'sunrise' | 'sunset'
    window_id: str
    capture_window_start_utc: str  # ISO8601 with 'Z' suffix
    capture_window_end_utc: str
    capture_interval_s: float
    log_level: str


_REQUIRED = (
    "camera_id",
    "device_token",
    "api_base",
    "phase",
    "window_id",
    "capture_window_start_utc",
    "capture_window_end_utc",
    "capture_interval_s",
)

# The minimal identity a device needs to come ONLINE (register + heartbeat). A
# freshly-provisioned, unplaced unit only has these; it gets the capture config
# (phase/window) after placement, before it goes ACTIVE.
_IDENTITY_REQUIRED = (
    "camera_id",
    "device_token",
    "api_base",
)


def _parse_iso(value: str) -> datetime:
    # Python's fromisoformat accepts '+00:00' but not 'Z' (until 3.11+ does).
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_config(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config not found: {p}")

    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc

    for key in _REQUIRED:
        if key not in raw:
            raise ConfigError(f"missing required key: {key}")

    if raw["phase"] not in ("sunrise", "sunset"):
        raise ConfigError(f"phase must be sunrise or sunset, got {raw['phase']!r}")

    try:
        _parse_iso(raw["capture_window_start_utc"])
        _parse_iso(raw["capture_window_end_utc"])
    except ValueError as exc:
        raise ConfigError(f"capture_window_*_utc must be ISO8601: {exc}") from exc

    raw.setdefault("log_level", "INFO")
    return raw  # type: ignore[return-value]


def load_identity(path: str | Path) -> dict:
    """Load the minimal identity for the ONLINE/IDLE loop (register + heartbeat).

    Unlike :func:`load_config`, this does NOT require the capture config
    (phase/window/capture_window) — a provisioned-but-unplaced device only has
    identity and must come online to *request* its placement. The supervisor uses
    this; the capture loop (``sunset_cam.main``) keeps the strict ``load_config``.
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config not found: {p}")

    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc

    for key in _IDENTITY_REQUIRED:
        if key not in raw:
            raise ConfigError(f"missing required identity key: {key}")

    raw.setdefault("log_level", "INFO")
    return raw
