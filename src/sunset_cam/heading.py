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


class HeadingState:
    """Tracks heading confidence. Three states:
    - 'uncalibrated': no valid tap yet -> overlay draws nothing speculative.
    - 'tapped': valid heading anchored.
    - 'suspect': housing tilt drifted from tap-time -> ask for a re-tap."""

    def __init__(
        self, hfov_deg: float, width: int,
        level_tol_deg: float = 5.0, drift_tol_deg: float = 3.0,
    ) -> None:
        self._hfov = hfov_deg
        self._width = width
        self._level_tol = level_tol_deg
        self._drift_tol = drift_tol_deg
        self._heading: float | None = None
        self._tap_roll: float | None = None
        self._tap_pitch: float | None = None
        self._suspect = False

    def apply_tap(
        self, sun_azimuth_deg: float, tap_px_x: float, roll_deg: float, pitch_deg: float
    ) -> bool:
        """Anchor heading from a sun-tap. Refuses (returns False) if the camera
        isn't level enough for the horizontal-pixel->azimuth mapping to hold."""
        if abs(roll_deg) > self._level_tol or abs(pitch_deg) > self._level_tol:
            return False
        self._heading = heading_from_tap(sun_azimuth_deg, tap_px_x, self._width, self._hfov)
        self._tap_roll, self._tap_pitch = roll_deg, pitch_deg
        self._suspect = False
        return True

    def update_orientation(self, roll_deg: float, pitch_deg: float) -> None:
        """Called as live roll/pitch arrive. Flags suspect if tilt drifted
        from its value at tap-time (the housing moved)."""
        if self._heading is None:
            return
        if (abs(roll_deg - self._tap_roll) > self._drift_tol
                or abs(pitch_deg - self._tap_pitch) > self._drift_tol):
            self._suspect = True

    def status(self) -> str:
        if self._heading is None:
            return "uncalibrated"
        return "suspect" if self._suspect else "tapped"

    def heading_deg(self) -> float | None:
        return self._heading
