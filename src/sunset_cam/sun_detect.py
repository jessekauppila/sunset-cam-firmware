"""Sun-centroid detection for live auto-track aiming. Pure + hardware-free:
operates on a 2D grayscale array so it unit-tests with synthetic frames. The
Pi-side glue (picamera2 -> grayscale) is injected separately.

The sun saturates the sensor to a bright disk, so we require an absolute
brightness floor (rejects flat/dim frames with no sun) and then take the
centroid of the brightest region.
"""
from __future__ import annotations


def detect_sun_centroid(
    gray: "object", abs_floor: int = 230, rel: float = 0.9, min_pixels: int = 12
) -> tuple[float, float] | None:
    """Return the (cx, cy) pixel centroid of the sun, or None if not found.

    - `abs_floor`: peak brightness must reach this for a sun to be present
      (a flat dim frame -> None).
    - `rel`: the bright region is pixels >= rel * peak.
    - `min_pixels`: too few bright pixels -> None (noise, not the sun).
    """
    import numpy as np  # lazy: keeps module import safe if numpy is absent

    peak = int(gray.max())
    if peak < abs_floor:
        return None
    ys, xs = np.where(gray >= rel * peak)
    if xs.size < min_pixels:
        return None
    return (float(xs.mean()), float(ys.mean()))
