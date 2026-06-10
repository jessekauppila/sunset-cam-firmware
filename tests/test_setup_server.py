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

def test_tap_accepts_at_configured_mount_reference():
    # cam1: IMU rotated 90deg, reads roll -90 when correctly mounted
    svc = AimingService(
        lat=48.7519, lng=-122.4787, phase="sunset", hfov_deg=120.0, width=1600,
        frame_source=lambda: b"\xff\xd8\xff\xd9", reader=lambda: (-90.0, 0.0),
        now_utc_fn=lambda: datetime(2026, 6, 21, 3, 30, tzinfo=timezone.utc),
        mount_roll_ref_deg=-90.0, mount_pitch_ref_deg=0.0, level_tol_deg=15.0,
    )
    body, status, _ = svc.handle_post("/setup/tap", {"pixel_x": 800, "pixel_y": 450})
    assert status == 200
    assert json.loads(body)["status"] == "tapped"

def test_orientation_json_returns_live_roll_pitch():
    body, status, _ = _service().handle_get("/setup/orientation.json")
    assert status == 200
    assert json.loads(body)["roll_deg"] == 0.2

def test_preview_returns_503_when_camera_busy():
    def boom():
        raise RuntimeError("camera in use")
    assert _service(frame_source=boom).preview_status() == 503

def test_confirm_in_tapped_state_returns_placement():
    sink = []
    svc = AimingService(
        lat=48.7519, lng=-122.4787, phase="sunset", hfov_deg=120.0, width=1600,
        frame_source=lambda: b"\xff\xd8\xff\xd9", reader=lambda: (0.2, 1.0),
        now_utc_fn=lambda: datetime(2026, 6, 21, 3, 30, tzinfo=timezone.utc),
        placement_sink=sink.append,
    )
    svc.handle_post("/setup/tap", {"pixel_x": 800, "pixel_y": 450})  # -> tapped
    body, status, _ = svc.handle_post("/setup/confirm", {})
    assert status == 200
    data = json.loads(body)
    assert data["status"] == "confirmed"
    assert data["placement"]["azimuth_deg"] == svc.state.heading_deg()
    assert data["placement"]["tilt_deg"] == 1.0
    assert data["placement"]["roll_deg"] == 0.2
    assert "confirmed_at" in data["placement"]
    assert sink == [data["placement"]]

def test_confirm_without_tap_returns_409():
    svc = AimingService(
        lat=48.0, lng=-122.0, phase="sunset", hfov_deg=120.0, width=1600,
        frame_source=lambda: b"\xff\xd8\xff\xd9", reader=lambda: (0.0, 0.0),
        now_utc_fn=lambda: datetime(2026, 6, 21, 3, 30, tzinfo=timezone.utc),
        placement_sink=lambda p: None,
    )
    body, status, _ = svc.handle_post("/setup/confirm", {})
    assert status == 409
