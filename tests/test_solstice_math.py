"""Tests for the solstice / sun-azimuth math.

Uses NOAA-tabulated solstice sunset azimuths to validate the formula at a
known latitude (Bellingham, WA: 48.7519°N).
"""
from __future__ import annotations

from sunset_cam.solstice_math import (
    sunset_azimuth_for_day,
    az_to_pixel,
    count_sunsets_in_fov,
)


# Bellingham, WA
BELLINGHAM_LAT = 48.7519
BELLINGHAM_LNG = -122.4787


def test_sunset_azimuth_june_solstice_bellingham_is_northwest():
    # June 21 sunset at 48.75°N is ~302° refraction-corrected; geometric
    # approximation lands a few degrees lower. Bound is intentionally wide
    # to reflect "±5° good-enough" accuracy at high latitudes.
    az = sunset_azimuth_for_day(BELLINGHAM_LAT, 2026, 6, 21)
    assert 290.0 <= az <= 310.0


def test_sunset_azimuth_december_solstice_bellingham_is_southwest():
    # Dec 21 sunset at 48.75°N is ~238° refraction-corrected; geometric
    # approximation gives ~233° (5° lower; see module docstring).
    az = sunset_azimuth_for_day(BELLINGHAM_LAT, 2026, 12, 21)
    assert 228.0 <= az <= 245.0


def test_sunset_azimuth_equinox_bellingham_is_near_due_west():
    # Mar/Sep equinox sunset is always ~270° (within ~1°).
    az_sep = sunset_azimuth_for_day(BELLINGHAM_LAT, 2026, 9, 22)
    assert 268.0 <= az_sep <= 272.0


def test_az_to_pixel_center_when_target_equals_camera_center():
    # If the target azimuth equals the camera's center, it maps to screen center.
    px = az_to_pixel(az_deg=270.0, center_az=270.0, fov_deg=102.0, screen_width=1600)
    assert abs(px - 800.0) < 1.0


def test_az_to_pixel_wraps_signed_delta_correctly():
    # Camera at 350°, target at 10°: signed delta should be +20°, not -340°.
    px = az_to_pixel(az_deg=10.0, center_az=350.0, fov_deg=102.0, screen_width=1600)
    # +20°/102° of full width → 800 + 1600*(20/102) ≈ 1114
    assert 1100 <= px <= 1130


def test_count_sunsets_in_fov_bellingham_west_returns_full_year():
    # West-facing camera with 102° FOV centered on 270° covers
    # roughly 219°–321°. Bellingham's sunset azimuth range over a year
    # is roughly 240°–302°, fully inside the FOV → 365 days.
    count = count_sunsets_in_fov(
        BELLINGHAM_LAT, BELLINGHAM_LNG,
        center_az=270.0, fov_deg=102.0, year=2026,
    )
    assert count == 365


def test_count_sunsets_in_fov_bellingham_north_returns_few():
    # North-facing camera misses every sunset. Expect 0.
    count = count_sunsets_in_fov(
        BELLINGHAM_LAT, BELLINGHAM_LNG,
        center_az=0.0, fov_deg=60.0, year=2026,
    )
    assert count == 0
