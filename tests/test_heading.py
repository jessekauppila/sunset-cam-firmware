from sunset_cam.heading import pixel_offset_to_angle, heading_from_tap, HeadingState

def test_pixel_center_is_zero_offset():
    assert pixel_offset_to_angle(px_x=800, width=1600, hfov_deg=120.0) == 0.0

def test_pixel_right_edge_is_plus_half_fov():
    assert abs(pixel_offset_to_angle(1600, 1600, 120.0) - 60.0) < 1e-9

def test_pixel_left_edge_is_minus_half_fov():
    assert abs(pixel_offset_to_angle(0, 1600, 120.0) - (-60.0)) < 1e-9

def test_heading_from_tap_subtracts_offset_from_sun_azimuth():
    # Sun at azimuth 300; appears at +20 deg (right of center) -> camera points at 280.
    h = heading_from_tap(sun_azimuth_deg=300.0, tap_px_x=1066.67, width=1600, hfov_deg=120.0)
    assert abs(h - 280.0) < 0.1


def test_starts_uncalibrated():
    s = HeadingState(hfov_deg=120.0, width=1600)
    assert s.status() == "uncalibrated"
    assert s.heading_deg() is None

def test_becomes_tapped_after_apply_tap():
    s = HeadingState(hfov_deg=120.0, width=1600)
    s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=0.2, pitch_deg=1.0)
    assert s.status() == "tapped"
    assert abs(s.heading_deg() - 300.0) < 0.1

def test_rejects_tap_when_not_level():
    s = HeadingState(hfov_deg=120.0, width=1600, level_tol_deg=5.0)
    ok = s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=20.0, pitch_deg=0.0)
    assert ok is False
    assert s.status() == "uncalibrated"

def test_becomes_suspect_when_tilt_drifts_from_tap_time():
    s = HeadingState(hfov_deg=120.0, width=1600, drift_tol_deg=3.0)
    s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=0.0, pitch_deg=0.0)
    s.update_orientation(roll_deg=10.0, pitch_deg=0.0)
    assert s.status() == "suspect"
