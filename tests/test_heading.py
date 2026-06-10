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


# --- mount-referenced level gate (IMU rotated 90deg vs a landscape camera) ---

def _mounted_state():
    return HeadingState(
        hfov_deg=120.0, width=1600,
        mount_roll_ref_deg=-90.0, mount_pitch_ref_deg=0.0, level_tol_deg=15.0,
    )

def test_tap_accepted_at_mount_reference():
    # correctly mounted cam1 reads roll -90 / pitch 0
    s = _mounted_state()
    ok = s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=-90.0, pitch_deg=0.0)
    assert ok is True
    assert s.status() == "tapped"

def test_tap_accepted_within_tolerance_of_reference():
    s = _mounted_state()
    # 12 deg off roll, 10 off pitch -> inside +/-15
    ok = s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=-78.0, pitch_deg=10.0)
    assert ok is True

def test_tap_refused_beyond_tolerance_of_reference():
    s = _mounted_state()
    # 20 deg off roll -> outside +/-15
    ok = s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=-70.0, pitch_deg=0.0)
    assert ok is False
    assert s.status() == "uncalibrated"

def test_flat_zero_refused_when_reference_is_minus_90():
    # the old "level" (roll 0) is now off-reference and must be refused
    s = _mounted_state()
    assert s.apply_tap(sun_azimuth_deg=300.0, tap_px_x=800.0, roll_deg=0.0, pitch_deg=0.0) is False


# --- direct heading anchor (phone compass / manual dial) ---

def test_apply_heading_sets_heading_directly_when_level():
    s = _mounted_state()
    ok = s.apply_heading(heading_deg=250.0, roll_deg=-90.0, pitch_deg=0.0)
    assert ok is True
    assert s.status() == "tapped"
    assert abs(s.heading_deg() - 250.0) < 1e-9

def test_apply_heading_refused_off_level():
    s = _mounted_state()
    ok = s.apply_heading(heading_deg=250.0, roll_deg=0.0, pitch_deg=0.0)  # off the -90 ref
    assert ok is False
    assert s.status() == "uncalibrated"

def test_apply_heading_normalizes_mod_360():
    s = _mounted_state()
    s.apply_heading(heading_deg=400.0, roll_deg=-90.0, pitch_deg=0.0)
    assert abs(s.heading_deg() - 40.0) < 1e-9
