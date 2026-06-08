from sunset_cam.heading import pixel_offset_to_angle, heading_from_tap

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
