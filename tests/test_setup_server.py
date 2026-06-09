import json
from datetime import datetime, timezone
from sunset_cam.setup_server import AimingService

def _service(frame_source=None):
    return AimingService(
        lat=48.7519, lng=-122.4787, phase="sunset", hfov_deg=120.0, width=1600,
        frame_source=frame_source or (lambda: b"\xff\xd8fakejpeg\xff\xd9"),
        reader=lambda: (0.2, 1.0),
        now_utc_fn=lambda: datetime(2026, 6, 21, 3, 30, tzinfo=timezone.utc),
    )

def test_state_json_starts_uncalibrated():
    body, status, ctype = _service().handle_get("/setup/state.json")
    assert status == 200 and "application/json" in ctype
    assert json.loads(body)["status"] == "uncalibrated"

def test_tap_sets_heading_and_returns_fit():
    body, status, _ = _service().handle_post("/setup/tap", {"pixel_x": 800, "pixel_y": 450})
    assert status == 200
    data = json.loads(body)
    assert data["status"] == "tapped"
    assert "heading_deg" in data and "fits" in data

def test_orientation_json_returns_live_roll_pitch():
    body, status, _ = _service().handle_get("/setup/orientation.json")
    assert status == 200
    assert json.loads(body)["roll_deg"] == 0.2

def test_preview_returns_503_when_camera_busy():
    def boom():
        raise RuntimeError("camera in use")
    assert _service(frame_source=boom).preview_status() == 503
