from sunset_cam.supervisor import decide_mode, run_once

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
