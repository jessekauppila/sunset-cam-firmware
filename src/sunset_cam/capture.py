"""picamera2 wrapper. Lazy-imports the C library so non-Pi dev machines
can still import the package.
"""

from __future__ import annotations

import io
import time
from typing import Any


_camera: Any | None = None

# Seconds to let auto-exposure and white balance settle after start() before the
# first frame is trusted. The camera is now opened at every window start, so
# without this the first frame of every window is dark or green.
WARMUP_S = 2.0


def _get_camera() -> Any:
    global _camera
    if _camera is not None:
        return _camera

    from picamera2 import Picamera2  # noqa: WPS433 (lazy import)

    cam = Picamera2()
    cfg = cam.create_still_configuration(main={"size": (1920, 1080)})
    cam.configure(cfg)
    cam.start()
    time.sleep(WARMUP_S)
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
    """Release the camera so it can be reopened later in this process.

    Must call close(), not stop(): in picamera2, stop() halts frames but leaves
    the libcamera device acquired and the instance registered with the
    CameraManager, so the next Picamera2() in the same process fails with
    "Camera __init__ sequence did not complete". Only close() releases it.
    """
    global _camera
    if _camera is not None:
        try:
            _camera.close()
        except Exception:  # noqa: BLE001
            pass
        _camera = None
