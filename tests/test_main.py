import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sunset_cam.main import tick
from sunset_cam.profiles import profiles_from_config

LOG = logging.getLogger("test")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


CLOUD_CFG = {
    "camera_id": 7,
    "profiles": [
        {
            "name": "clouds",
            "window": {"daily_utc": {"start": "16:00", "end": "01:00"}},
            "interval_s": 300,
            "sink": {"kind": "welkin", "url": "http://h:8000"},
        }
    ],
}

LEGACY_CFG = {
    "camera_id": 42,
    "device_token": "tok",
    "api_base": "https://sunrisesunset.studio",
    "phase": "sunset",
    "window_id": "w1",
    "capture_window_start_utc": "2026-05-03T01:00:00Z",
    "capture_window_end_utc": "2026-05-03T02:30:00Z",
    "capture_interval_s": 1.0,
}


class Clock:
    """Returns the given times in order, then repeats the last."""

    def __init__(self, *times: datetime) -> None:
        self.times = list(times)

    def __call__(self) -> datetime:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, datetime]] = []
        self.released = 0

    def capture(self) -> bytes:
        return b"jpeg"

    def send(self, config: dict, profile, jpeg: bytes, at: datetime) -> dict:
        self.sent.append((profile.name, at))
        return {}

    def release(self) -> None:
        self.released += 1


def run_tick(cfg: dict, clock: Clock, rec: Recorder) -> float:
    return tick(
        cfg,
        profiles_from_config(cfg),
        LOG,
        clock=clock,
        capture=rec.capture,
        send=rec.send,
        release=rec.release,
    )


def test_inside_a_cloud_window_captures_and_sleeps_to_the_next_five_minute_mark() -> None:
    rec = Recorder()
    # Capture starts 20:05:00, work finishes 20:05:02.
    delay = run_tick(CLOUD_CFG, Clock(utc(2026, 9, 18, 20, 5, 0), utc(2026, 9, 18, 20, 5, 2)), rec)
    assert rec.sent == [("clouds", utc(2026, 9, 18, 20, 5, 0))]
    assert delay == pytest.approx(298.0)


def test_early_wakeup_does_not_capture_twice_for_one_tick() -> None:
    rec = Recorder()
    # Woke 3 ms before 20:05:00 and the work was instant.
    early = utc(2026, 9, 18, 20, 4, 59) + timedelta(microseconds=997_000)
    delay = run_tick(CLOUD_CFG, Clock(early, early), rec)
    assert delay > 290  # next capture is 20:10, not 20:05
    assert len(rec.sent) == 1


def test_outside_every_window_releases_the_camera_and_polls() -> None:
    rec = Recorder()
    delay = run_tick(CLOUD_CFG, Clock(utc(2026, 9, 18, 12, 0)), rec)
    assert rec.sent == []
    assert rec.released == 1
    assert delay == 30.0


def test_legacy_config_keeps_todays_fixed_interval_after_work() -> None:
    rec = Recorder()
    delay = run_tick(LEGACY_CFG, Clock(utc(2026, 5, 3, 1, 30, 0), utc(2026, 5, 3, 1, 30, 0, 400_000)), rec)
    assert rec.sent == [("sunset", utc(2026, 5, 3, 1, 30, 0))]
    assert delay == 1.0


def test_capture_failure_is_logged_and_the_loop_keeps_its_cadence() -> None:
    rec = Recorder()

    def boom() -> bytes:
        raise RuntimeError("camera not detected")

    delay = tick(
        CLOUD_CFG,
        profiles_from_config(CLOUD_CFG),
        LOG,
        clock=Clock(utc(2026, 9, 18, 20, 5, 0), utc(2026, 9, 18, 20, 5, 1)),
        capture=boom,
        send=rec.send,
        release=rec.release,
    )
    assert rec.sent == []
    assert delay == pytest.approx(299.0)


def test_upload_failure_does_not_stop_the_loop() -> None:
    def refuse(*_a: object) -> dict:
        raise RuntimeError("HTTP 500")

    delay = tick(
        CLOUD_CFG,
        profiles_from_config(CLOUD_CFG),
        LOG,
        clock=Clock(utc(2026, 9, 18, 20, 5, 0), utc(2026, 9, 18, 20, 5, 1)),
        capture=lambda: b"jpeg",
        send=refuse,
        release=lambda: None,
    )
    assert delay == pytest.approx(299.0)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_ends_a_long_idle_wait_promptly(tmp_path: Path) -> None:
    # A cloud-only config outside its window: the loop waits 30 s between
    # polls. SIGTERM must end that wait at once, not after it (systemd would
    # SIGKILL a 300 s sleep).
    cfg = dict(CLOUD_CFG)
    now = datetime.now(timezone.utc)
    closed = (now + timedelta(hours=2)).strftime("%H:%M"), (now + timedelta(hours=3)).strftime("%H:%M")
    cfg["profiles"] = [dict(CLOUD_CFG["profiles"][0], window={"daily_utc": {"start": closed[0], "end": closed[1]}})]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "sunset_cam.main", str(path)],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        # Wait for the startup log line so the handler is installed.
        line = ""
        while "starting" not in line and time.monotonic() < deadline:
            line = proc.stderr.readline()
        assert "starting" in line
        time.sleep(0.3)
        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=5) == 0
        assert time.monotonic() - t0 < 2
    finally:
        if proc.poll() is None:
            proc.kill()
