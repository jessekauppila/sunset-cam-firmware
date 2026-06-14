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
