import numpy as np
from sunset_cam.sun_detect import detect_sun_centroid


def _frame(h=120, w=200, fill=40):
    return np.full((h, w), fill, dtype=np.uint8)


def test_centroid_of_a_bright_blob():
    g = _frame()
    g[50:60, 90:110] = 255          # 10x20 saturated patch, center at (x=99.5, y=54.5)
    c = detect_sun_centroid(g)
    assert c is not None
    cx, cy = c
    assert abs(cx - 99.5) < 1.0
    assert abs(cy - 54.5) < 1.0


def test_off_center_blob_gives_large_cx():
    g = _frame()
    g[10:25, 175:195] = 255         # near the right edge
    cx, cy = detect_sun_centroid(g)
    assert cx > 180


def test_dim_frame_returns_none():
    g = _frame(fill=150)            # bright-ish sky but no saturated sun
    g[5:15, 5:15] = 200             # still below the absolute floor
    assert detect_sun_centroid(g) is None


def test_too_few_bright_pixels_returns_none():
    g = _frame()
    g[0:2, 0:2] = 255              # only 4 saturated pixels (< min_pixels)
    assert detect_sun_centroid(g) is None
