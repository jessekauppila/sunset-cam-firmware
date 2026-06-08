"""Sun-tap heading math: convert a tapped sun pixel + the sun's true azimuth
into the camera's compass heading. No magnetometer; pinhole approximation
adequate for aiming (lens-distortion correction is a v0.3-grade refinement)."""
from __future__ import annotations


def pixel_offset_to_angle(px_x: float, width: int, hfov_deg: float) -> float:
    """Horizontal angle (deg) of a pixel from frame center. Center=0,
    right edge=+hfov/2, left edge=-hfov/2 (azimuth increases to the right
    for a normal forward-facing, non-mirrored camera)."""
    return ((px_x - width / 2.0) / width) * hfov_deg


def heading_from_tap(
    sun_azimuth_deg: float, tap_px_x: float, width: int, hfov_deg: float
) -> float:
    """Camera heading (compass deg) = sun's true azimuth minus where the sun
    appears in the frame. apparent_angle = azimuth - heading, so
    heading = azimuth - apparent_angle."""
    offset = pixel_offset_to_angle(tap_px_x, width, hfov_deg)
    return (sun_azimuth_deg - offset) % 360.0
