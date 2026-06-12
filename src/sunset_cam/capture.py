"""picamera2 wrapper. Lazy-imports the C library so non-Pi dev machines
can still import the package.
"""

from __future__ import annotations

import io
from typing import Any


_camera: Any | None = None


def _get_camera() -> Any:
    global _camera
    if _camera is not None:
        return _camera

    from picamera2 import Picamera2  # noqa: WPS433 (lazy import)

    cam = Picamera2()
    cfg = cam.create_still_configuration(main={"size": (1920, 1080)})
    cam.configure(cfg)
    cam.start()
    _camera = cam
    return cam


def capture_jpeg() -> bytes:
    cam = _get_camera()
    buf = io.BytesIO()
    # If older picamera2 on the deployment Pi rejects this BytesIO target,
    # the fallback is: cam.capture_image("main").save(buf, format="JPEG").
    cam.capture_file(buf, format="jpeg")
    return buf.getvalue()


def capture_gray_array(stride: int = 8):
    """Downsampled 2D grayscale (uint8) of the current frame, for sun detection.
    Strided to keep the Pi Zero 2 W responsive alongside the MJPEG preview.
    Returns None if the camera or numpy is unavailable (auto-track then no-ops)."""
    try:
        import numpy as np  # noqa: WPS433 (lazy; numpy ships with picamera2)

        cam = _get_camera()
        arr = cam.capture_array("main")          # H x W x {3,4} RGB(A)
        small = arr[::stride, ::stride, :3]
        return small.mean(axis=2).astype(np.uint8)
    except Exception:  # noqa: BLE001 — detection is best-effort
        return None


def shutdown() -> None:
    global _camera
    if _camera is not None:
        try:
            _camera.stop()
        except Exception:  # noqa: BLE001
            pass
        _camera = None
