"""Entry point. Run with: python -m sunset_cam.main /etc/sunset-cam/config.json

One loop, any number of capture profiles (see :mod:`sunset_cam.profiles`).
Each pass asks which profile's window is open, captures one frame, sends it
to that profile's sink, and sleeps until the next capture. Outside every
window the camera is released and the loop polls for the next opening.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sunset_cam.config import load_config
from sunset_cam.profiles import (
    Profile,
    active_profile,
    idle_poll_s,
    profiles_from_config,
    seconds_until_next_capture,
)
from sunset_cam.upload import send_frame

# Set by SIGTERM/SIGINT. Sleeping on an Event rather than time.sleep() means a
# stop request ends a 300 s wait at once instead of outlasting systemd's
# stop timeout and getting SIGKILLed mid-capture.
_stop = threading.Event()


def _handle_sigterm(_signum: int, _frame: object) -> None:
    _stop.set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _capture() -> bytes:
    from sunset_cam.capture import capture_jpeg

    return capture_jpeg()


def _release() -> None:
    from sunset_cam.capture import shutdown

    shutdown()


def tick(
    config: dict,
    profiles: list[Profile],
    log: logging.Logger,
    *,
    clock: Callable[[], datetime] = _utcnow,
    capture: Callable[[], bytes] = _capture,
    send: Callable[[dict, Profile, bytes, datetime], dict] = send_frame,
    release: Callable[[], None] = _release,
) -> float:
    """One pass of the capture loop. Returns seconds to sleep before the next."""
    now = clock()
    profile = active_profile(profiles, now)
    if profile is None:
        try:
            release()
        except Exception:  # noqa: BLE001 — releasing an idle camera is best-effort
            pass
        log.debug("no profile active; polling again in %.0fs", idle_poll_s(profiles))
        return idle_poll_s(profiles)

    try:
        jpeg = capture()
    except Exception as exc:  # noqa: BLE001
        log.error("[%s] capture failed: %s", profile.name, exc)
        return seconds_until_next_capture(profile, clock())

    try:
        ack = send(config, profile, jpeg, now)
        log.info("[%s] sent bytes=%d -> %s ack=%s", profile.name, len(jpeg), profile.sink["kind"], ack)
    except Exception as exc:  # noqa: BLE001
        log.error("[%s] upload failed: %s", profile.name, exc)

    return seconds_until_next_capture(profile, clock())


def run(config_path: str | Path) -> int:
    config = load_config(config_path)
    profiles = profiles_from_config(config)

    logging.basicConfig(
        level=getattr(logging, config["log_level"].upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("sunset_cam")
    log.info(
        "starting; camera_id=%s profiles=%s",
        config["camera_id"],
        ", ".join(f"{p.name}:{p.interval_s:g}s->{p.sink['kind']}" for p in profiles),
    )

    _stop.clear()
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    while not _stop.is_set():
        _stop.wait(tick(config, profiles, log))

    log.info("shutdown signal received; exiting cleanly")
    try:
        _release()
    except Exception:  # noqa: BLE001
        pass
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m sunset_cam.main /path/to/config.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1]))


if __name__ == "__main__":
    main()
