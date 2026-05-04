"""Tier 0 capture-window check.

v0 reads two hardcoded UTC ISO timestamps from config and answers
'is now between them'. Solar geometry (astral, NOAA SPA) is reserved
for Tier 1.
"""

from __future__ import annotations

from datetime import datetime


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_active_now(config: dict, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    start = _parse(config["capture_window_start_utc"])
    end = _parse(config["capture_window_end_utc"])
    return start <= now < end
