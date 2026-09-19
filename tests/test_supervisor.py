import logging

import pytest

from sunset_cam.supervisor import (
    decide_mode,
    online_placement_decision,
    register_on_start,
    run_directives,
    run_once,
)


def test_run_directives_executes_new_and_skips_already_seen():
    seen = set()
    calls = []
    def fake_exec(d):
        calls.append(d["id"])
        return {"id": d["id"], "status": "done"}
    out = run_directives(
        [{"id": "d1", "type": "ship-logs"}, {"id": "d2", "type": "x"}], fake_exec, seen,
    )
    assert [r["id"] for r in out] == ["d1", "d2"]
    assert seen == {"d1", "d2"}
    # same ids on the next poll are not re-executed (idempotent)
    out2 = run_directives([{"id": "d1", "type": "ship-logs"}], fake_exec, seen)
    assert out2 == []
    assert calls == ["d1", "d2"]

def test_run_directives_tolerates_none_and_empty():
    assert run_directives(None, lambda d: None, set()) == []
    assert run_directives([], lambda d: None, set()) == []

def test_decide_mode_maps_status():
    assert decide_mode("awaiting_aim") == "aiming"
    assert decide_mode("ready") == "capture"
    assert decide_mode("awaiting_location") == "idle"
    assert decide_mode(None) == "idle"

class FakeController:
    def __init__(self): self.mode = None
    def set_mode(self, m): self.mode = m

def test_run_once_aiming_writes_location_and_sets_aiming():
    written = []
    ctrl = FakeController()
    mode = run_once(
        status_source=lambda: {"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4},
        controller=ctrl,
        config_writer=lambda lat, lng: written.append((lat, lng)),
    )
    assert mode == "aiming"
    assert written == [(48.7, -122.4)]
    assert ctrl.mode == "aiming"

def test_run_once_ready_sets_capture_without_writing_location():
    written = []
    ctrl = FakeController()
    mode = run_once(
        status_source=lambda: {"placement_status": "ready", "lat": 48.7, "lng": -122.4},
        controller=ctrl,
        config_writer=lambda lat, lng: written.append((lat, lng)),
    )
    assert mode == "capture"
    assert written == []
    assert ctrl.mode == "capture"

def test_run_once_awaiting_location_is_idle():
    ctrl = FakeController()
    mode = run_once(
        status_source=lambda: {"placement_status": "awaiting_location", "lat": None, "lng": None},
        controller=ctrl, config_writer=lambda lat, lng: None,
    )
    assert mode == "idle" and ctrl.mode == "idle"


# ---------------------------------------------------------------------------
# register_on_start
# ---------------------------------------------------------------------------

def test_register_on_start_calls_register_fn_and_returns_result():
    cfg = {"camera_id": 1}
    expected = {"camera_id": 1, "placement_status": "awaiting_aim", "placement": None}
    calls = []

    def fake_register(config):
        calls.append(config)
        return expected

    result = register_on_start(cfg, register_fn=fake_register)
    assert result == expected
    assert calls == [cfg]


def test_register_on_start_returns_empty_dict_on_exception():
    cfg = {"camera_id": 1}

    def boom(config):
        raise RuntimeError("network down")

    result = register_on_start(cfg, register_fn=boom)
    assert result == {}


def test_register_on_start_logs_error_on_exception(caplog):
    cfg = {"camera_id": 1}

    def boom(config):
        raise ValueError("bad response")

    with caplog.at_level(logging.ERROR, logger="supervisor"):
        result = register_on_start(cfg, register_fn=boom)

    assert result == {}
    assert any("register" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# online_placement_decision
# ---------------------------------------------------------------------------

def test_online_placement_decision_awaiting_aim_gives_aiming_and_await():
    parsed = {"placement_status": "awaiting_aim", "coarse": None}
    mode, verb = online_placement_decision(parsed)
    assert mode == "aiming"
    assert verb == "AWAIT"


def test_online_placement_decision_ready_coarse_gives_capture_sun_self_refine():
    parsed = {"placement_status": "ready", "coarse": True}
    mode, verb = online_placement_decision(parsed)
    assert mode == "capture"
    assert verb == "SUN_SELF_REFINE"


def test_online_placement_decision_ready_precise_gives_capture_legacy_precise():
    parsed = {"placement_status": "ready", "coarse": False}
    mode, verb = online_placement_decision(parsed)
    assert mode == "capture"
    assert verb == "LEGACY_PRECISE"


def test_online_placement_decision_idle_status_gives_idle_and_await():
    parsed = {"placement_status": "awaiting_location", "coarse": None}
    mode, verb = online_placement_decision(parsed)
    assert mode == "idle"
    assert verb == "AWAIT"


# --- non-sunset profiles (review finding 3) --------------------------------------

import json  # noqa: E402

from sunset_cam import supervisor as sup  # noqa: E402
from sunset_cam.config import has_non_sunset_sink, has_sunset_sink  # noqa: E402

WELKIN_ONLY = {"camera_id": 7, "profiles": [
    {"name": "clouds", "window": {"daily_utc": {"start": "16:00", "end": "01:00"}}, "interval_s": 300,
     "sink": {"kind": "welkin", "url": "http://h:8000"}}]}
BOTH = {**WELKIN_ONLY, "device_token": "t", "api_base": "https://x", "profiles": WELKIN_ONLY["profiles"] + [
    {"name": "sunset", "window": {"daily_utc": {"start": "01:00", "end": "03:00"}}, "interval_s": 1,
     "sink": {"kind": "sunset", "phase": "sunset", "window_id": "w"}}]}
LEGACY = {"camera_id": 1, "device_token": "t", "api_base": "https://x", "phase": "sunset", "window_id": "w",
          "capture_window_start_utc": "2026-05-03T01:00:00Z", "capture_window_end_utc": "2026-05-03T02:00:00Z",
          "capture_interval_s": 1.0}


def test_sink_helpers_classify_configs() -> None:
    assert (has_sunset_sink(LEGACY), has_non_sunset_sink(LEGACY)) == (True, False)
    assert (has_sunset_sink(WELKIN_ONLY), has_non_sunset_sink(WELKIN_ONLY)) == (False, True)
    assert (has_sunset_sink(BOTH), has_non_sunset_sink(BOTH)) == (True, True)


class _Ctl:
    def __init__(self) -> None:
        self.modes: list[str] = []

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)


def test_run_once_keeps_capture_running_when_placement_is_idle_and_a_welkin_profile_exists() -> None:
    ctl = _Ctl()
    mode = sup.run_once(lambda: {"placement_status": "awaiting_location"}, ctl, lambda *a: None, keep_capture=True)
    assert mode == "capture" and ctl.modes == ["capture"]
    # Without the flag, today's behaviour: idle stops the capture unit.
    ctl = _Ctl()
    assert sup.run_once(lambda: {"placement_status": "awaiting_location"}, ctl, lambda *a: None) == "idle"


def test_run_once_keep_capture_still_yields_to_aiming() -> None:
    ctl = _Ctl()
    mode = sup.run_once(lambda: {"placement_status": "awaiting_aim", "lat": 1.0, "lng": 2.0}, ctl, lambda *a: None,
                        keep_capture=True)
    assert mode == "aiming"


def test_main_exits_cleanly_on_a_welkin_only_config_instead_of_crash_looping(tmp_path, monkeypatch, caplog) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(WELKIN_ONLY))
    monkeypatch.setattr(sup, "CONFIG_PATH", str(cfg))
    started = []
    monkeypatch.setattr(sup, "SystemctlController", lambda: started.append("controller"))
    with caplog.at_level("INFO"):
        sup.main(interval_s=0)  # returns instead of raising ConfigError
    assert started == []
    assert "nothing to supervise" in caplog.text


def test_main_still_fails_loudly_when_identity_is_missing_on_a_sunset_config(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"camera_id": 1, "profiles": BOTH["profiles"]}))  # sunset sink, no token
    monkeypatch.setattr(sup, "CONFIG_PATH", str(cfg))
    with pytest.raises(sup.ConfigError):
        sup.main(interval_s=0)
