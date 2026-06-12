from sunset_cam.supervisor import decide_mode, run_once, run_directives


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
