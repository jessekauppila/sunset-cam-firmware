"""Capture profiles: a window, a cadence and a sink, as one unit.

A device runs one or more profiles. At any moment at most one is active; the
capture loop asks :func:`active_profile` which, captures a frame, and sends it
to that profile's sink. Sunset and cloud windows do not overlap within a day,
so one loop with no concurrency is enough. Overlapping daily windows are
rejected at load time.

Config shape (``config.json``)::

    {
      "camera_id": 3,
      "profiles": [
        {"name": "clouds",
         "window": {"daily_utc": {"start": "16:00", "end": "01:00"}},
         "interval_s": 300,
         "sink": {"kind": "welkin", "url": "http://192.168.1.20:8000"}}
      ]
    }

Windows:
  ``daily_utc``    repeats every day; ``start > end`` wraps midnight UTC.
  ``absolute_utc`` one ISO8601 range, the original Tier 0 window.

Sinks:
  ``welkin``  raw JPEG to ``POST {url}/frames/{camera_id}``; optional ``token``.
  ``sunset``  the parent app's snapshot endpoint; needs top-level ``api_base``
              and ``device_token`` plus the sink's ``phase`` and ``window_id``.

``align_to_clock`` (default true) schedules captures on wall-clock multiples
of ``interval_s`` (a 300 s profile captures at :00, :05, :10 ...), so frames
from different cameras line up and gaps are easy to spot.

A config with no ``profiles`` key is a legacy Tier 0 config. It becomes a
single profile named ``sunset`` built from the flat keys, with
``align_to_clock`` false, so it behaves exactly as before.

Solar-computed windows (terminator for sunsets, high sun for clouds) are Tier 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Union

IDLE_POLL_MAX_S = 30.0


class ProfileError(ValueError):
    """Raised when a profile in config.json is invalid."""


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")


@dataclass(frozen=True)
class AbsoluteWindow:
    start: datetime
    end: datetime

    def contains(self, now: datetime) -> bool:
        _require_aware(now)
        return self.start <= now < self.end

    def next_boundary(self, now: datetime) -> datetime | None:
        """The next instant this window opens or closes, or None if it never will."""
        _require_aware(now)
        if now < self.start:
            return self.start
        if now < self.end:
            return self.end
        return None


@dataclass(frozen=True)
class DailyWindow:
    """UTC wall-clock window. ``start > end`` wraps midnight."""

    start: time
    end: time

    def contains(self, now: datetime) -> bool:
        _require_aware(now)
        t = now.astimezone(timezone.utc).time()
        if self.start < self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end

    def minutes(self) -> set[int]:
        s = self.start.hour * 60 + self.start.minute
        e = self.end.hour * 60 + self.end.minute
        if s < e:
            return set(range(s, e))
        return set(range(s, 24 * 60)) | set(range(0, e))

    def next_boundary(self, now: datetime) -> datetime:
        """The next instant this window opens (if outside) or closes (if inside)."""
        _require_aware(now)
        utc = now.astimezone(timezone.utc)
        target = self.end if self.contains(now) else self.start
        candidate = utc.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
        if candidate <= utc:
            candidate += timedelta(days=1)
        return candidate


Window = Union[AbsoluteWindow, DailyWindow]


@dataclass(frozen=True)
class Profile:
    name: str
    window: Window
    interval_s: float
    sink: dict
    align_to_clock: bool = True

    def is_active(self, now: datetime) -> bool:
        return self.window.contains(now)


# --- parsing --------------------------------------------------------------


def _parse_iso(value: object, where: str) -> datetime:
    if not isinstance(value, str):
        raise ProfileError(f"{where} must be an ISO8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileError(f"{where} must be ISO8601: {exc}") from exc
    if dt.tzinfo is None:
        raise ProfileError(f"{where} must carry a timezone (use a 'Z' suffix)")
    return dt


def _parse_hhmm(value: object, where: str) -> time:
    if isinstance(value, str):
        parts = value.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h < 24 and 0 <= m < 60:
                return time(h, m)
    raise ProfileError(f"{where} must be HH:MM in UTC, got {value!r}")


def _parse_window(raw: object, where: str) -> Window:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ProfileError(f"{where}.window must have exactly one of daily_utc, absolute_utc")
    [(kind, spec)] = raw.items()
    if not isinstance(spec, dict):
        raise ProfileError(f"{where}.window.{kind} must be an object with start and end")
    if kind == "daily_utc":
        start = _parse_hhmm(spec.get("start"), f"{where}.window.daily_utc.start")
        end = _parse_hhmm(spec.get("end"), f"{where}.window.daily_utc.end")
        if start == end:
            raise ProfileError(f"{where}.window.daily_utc is empty (start == end)")
        return DailyWindow(start=start, end=end)
    if kind == "absolute_utc":
        start_dt = _parse_iso(spec.get("start"), f"{where}.window.absolute_utc.start")
        end_dt = _parse_iso(spec.get("end"), f"{where}.window.absolute_utc.end")
        if end_dt <= start_dt:
            raise ProfileError(f"{where}.window.absolute_utc end must be after start")
        return AbsoluteWindow(start=start_dt, end=end_dt)
    raise ProfileError(f"{where}.window has unknown kind {kind!r}; use daily_utc or absolute_utc")


def _parse_sink(raw: object, where: str, config: dict) -> dict:
    if not isinstance(raw, dict):
        raise ProfileError(f"{where}.sink must be an object")
    kind = raw.get("kind")
    if kind == "welkin":
        url = raw.get("url")
        if not isinstance(url, str) or not url:
            raise ProfileError(f"{where}.sink.url is required for a welkin sink")
        if not url.startswith(("http://", "https://")):
            raise ProfileError(f"{where}.sink.url must start with http:// or https://")
        token = raw.get("token")
        if token is not None and not isinstance(token, str):
            raise ProfileError(f"{where}.sink.token must be a string")
        return dict(raw)
    if kind == "sunset":
        for key in ("api_base", "device_token"):
            if not config.get(key):
                raise ProfileError(f"{where}.sink kind 'sunset' needs top-level {key}")
        if raw.get("phase") not in ("sunrise", "sunset"):
            raise ProfileError(f"{where}.sink.phase must be sunrise or sunset, got {raw.get('phase')!r}")
        if not raw.get("window_id"):
            raise ProfileError(f"{where}.sink.window_id is required for a sunset sink")
        return dict(raw)
    raise ProfileError(f"{where}.sink.kind must be welkin or sunset, got {kind!r}")


def _parse_profile(raw: object, index: int, config: dict) -> Profile:
    where = f"profiles[{index}]"
    if not isinstance(raw, dict):
        raise ProfileError(f"{where} must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProfileError(f"{where}.name must be a non-empty string")
    where = f"profiles[{index}] ({name})"
    interval = raw.get("interval_s")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0:
        raise ProfileError(f"{where}.interval_s must be a positive number")
    align = raw.get("align_to_clock", True)
    if not isinstance(align, bool):
        raise ProfileError(f"{where}.align_to_clock must be true or false")
    return Profile(
        name=name,
        window=_parse_window(raw.get("window"), where),
        interval_s=float(interval),
        sink=_parse_sink(raw.get("sink"), where, config),
        align_to_clock=align,
    )


def _legacy_profile(config: dict) -> Profile:
    return Profile(
        name="sunset",
        window=AbsoluteWindow(
            start=_parse_iso(config["capture_window_start_utc"], "capture_window_start_utc"),
            end=_parse_iso(config["capture_window_end_utc"], "capture_window_end_utc"),
        ),
        interval_s=float(config["capture_interval_s"]),
        sink={"kind": "sunset", "phase": config["phase"], "window_id": config["window_id"]},
        align_to_clock=False,
    )


def profiles_from_config(config: dict) -> list[Profile]:
    """Parse and validate the profiles a config describes.

    Raises :class:`ProfileError` on anything the capture loop could not run.
    """
    if "profiles" not in config:
        return [_legacy_profile(config)]

    raw = config["profiles"]
    if not isinstance(raw, list) or not raw:
        raise ProfileError("profiles must be a list with at least one profile")
    profiles = [_parse_profile(p, i, config) for i, p in enumerate(raw)]

    seen: set[str] = set()
    for p in profiles:
        if p.name in seen:
            raise ProfileError(f"duplicate profile name {p.name!r}")
        seen.add(p.name)

    daily = [p for p in profiles if isinstance(p.window, DailyWindow)]
    for i, a in enumerate(daily):
        for b in daily[i + 1 :]:
            if a.window.minutes() & b.window.minutes():  # type: ignore[union-attr]
                raise ProfileError(f"profiles {a.name!r} and {b.name!r} have overlapping daily windows")
    return profiles


# --- scheduling -----------------------------------------------------------


def active_profile(profiles: list[Profile], now: datetime) -> Profile | None:
    """The first profile whose window contains ``now``, or None."""
    for p in profiles:
        if p.is_active(now):
            return p
    return None


def next_tick(now: datetime, interval_s: float) -> datetime:
    """The first wall-clock multiple of ``interval_s`` strictly after ``now``."""
    _require_aware(now)
    k = math.floor(now.timestamp() / interval_s) + 1
    return datetime.fromtimestamp(k * interval_s, tz=timezone.utc)


def seconds_until_next_capture(profile: Profile, after_work: datetime) -> float:
    """How long to sleep once a capture (and its upload) has finished.

    Aligned profiles wait for the next clock tick, but never past the end of
    their own window: the loop wakes at the boundary so the next profile can
    start on time (a 420 s cadence must not sleep through a 01:00 hand-off).
    The small lead guards against a timer that wakes a few ms early and would
    otherwise capture twice for one tick. Unaligned (legacy) profiles sleep a
    fixed interval after the work, as the Tier 0 loop always did.
    """
    if not profile.align_to_clock:
        return profile.interval_s
    lead = timedelta(seconds=min(1.0, profile.interval_s / 10))
    tick = next_tick(after_work + lead, profile.interval_s)
    boundary = profile.window.next_boundary(after_work)
    if boundary is not None and boundary < tick:
        tick = boundary
    return max(0.0, (tick - after_work).total_seconds())


def idle_poll_s(profiles: list[Profile], now: datetime | None = None) -> float:
    """How long to sleep when no window is open: until the earliest window
    opens, so the first frame lands on the opening minute, capped so a clock
    step or a config change is noticed within IDLE_POLL_MAX_S."""
    if now is None:
        return IDLE_POLL_MAX_S
    opens = [b for b in (p.window.next_boundary(now) for p in profiles) if b is not None]
    if not opens:
        return IDLE_POLL_MAX_S
    return max(0.0, min(IDLE_POLL_MAX_S, (min(opens) - now).total_seconds()))
