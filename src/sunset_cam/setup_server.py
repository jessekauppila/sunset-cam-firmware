"""Setup-server: a stdlib ThreadingHTTPServer that serves the aiming page,
the live MJPEG preview, live orientation, and the sun-tap endpoint. Logic
lives in AimingService (injectable, hardware-free) so it is unit-testable;
the HTTP handler is a thin adapter. Camera access is serialized by a lock."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from sunset_cam.heading import HeadingState
from sunset_cam.solstice_math import compute_sun_azimuth, fov_fit
from sunset_cam.setup_alignment import render_align_page, stream_mjpeg, MJPEG_BOUNDARY


DEFAULT_PLACEMENT_PATH = "/etc/sunset-cam/placement.json"


def _default_placement_sink(placement: dict) -> None:
    os.makedirs(os.path.dirname(DEFAULT_PLACEMENT_PATH), exist_ok=True)
    with open(DEFAULT_PLACEMENT_PATH, "w") as f:
        json.dump(placement, f)


class AimingService:
    def __init__(
        self, *, lat: float, lng: float, phase: str, hfov_deg: float, width: int,
        frame_source: Callable[[], bytes], reader: Callable[[], tuple[float, float]],
        now_utc_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        placement_sink: Callable[[dict], None] = _default_placement_sink,
    ) -> None:
        self.lat, self.lng, self.phase = lat, lng, phase
        self.hfov_deg, self.width = hfov_deg, width
        self.frame_source = frame_source
        self.reader = reader
        self.now_utc_fn = now_utc_fn
        self.placement_sink = placement_sink
        self.state = HeadingState(hfov_deg=hfov_deg, width=width)
        self._cam_lock = threading.Lock()

    def _orientation(self) -> tuple[float, float]:
        try:
            return self.reader()
        except Exception:
            return (0.0, 0.0)

    def _fit_payload(self) -> dict:
        roll, pitch = self._orientation()
        self.state.update_orientation(roll, pitch)
        payload = {"status": self.state.status(), "roll_deg": roll, "pitch_deg": pitch}
        h = self.state.heading_deg()
        if h is not None:
            year = self.now_utc_fn().year
            fit = fov_fit(self.lat, self.lng, h, self.hfov_deg, year)
            payload.update({"heading_deg": h, **fit})
        return payload

    def handle_get(self, path: str):
        if path in ("/", "/setup/align"):
            return render_align_page(self.lat, self.lng), 200, "text/html; charset=utf-8"
        if path == "/setup/orientation.json":
            roll, pitch = self._orientation()
            return json.dumps({"roll_deg": roll, "pitch_deg": pitch}), 200, "application/json"
        if path == "/setup/state.json":
            return json.dumps(self._fit_payload()), 200, "application/json"
        return json.dumps({"error": "not found"}), 404, "application/json"

    def handle_post(self, path: str, body: dict):
        if path == "/setup/tap":
            roll, pitch = self._orientation()
            sun_az = compute_sun_azimuth(self.lat, self.lng, self.now_utc_fn())
            ok = self.state.apply_tap(sun_az, float(body["pixel_x"]), roll, pitch)
            if not ok:
                return (json.dumps({"status": "uncalibrated", "error": "level the camera first"}),
                        422, "application/json")
            return json.dumps(self._fit_payload()), 200, "application/json"
        if path == "/setup/confirm":
            roll, pitch = self._orientation()
            self.state.update_orientation(roll, pitch)
            if self.state.status() != "tapped":
                return (json.dumps({"status": self.state.status(),
                                    "error": "aim not set — tap the sun first"}),
                        409, "application/json")
            placement = {
                "azimuth_deg": self.state.heading_deg(),
                "tilt_deg": pitch,
                "roll_deg": roll,
                "confirmed_at": self.now_utc_fn().isoformat(),
            }
            self.placement_sink(placement)
            return (json.dumps({"status": "confirmed", "placement": placement}),
                    200, "application/json")
        return json.dumps({"error": "not found"}), 404, "application/json"

    def preview_status(self) -> int:
        """200 if a frame can be grabbed, 503 if the camera is unavailable/busy."""
        with self._cam_lock:
            try:
                self.frame_source()
                return 200
            except Exception:
                return 503

    def mjpeg_frames(self, fps: int = 4):
        def locked_source() -> bytes:
            with self._cam_lock:
                return self.frame_source()
        for chunk in stream_mjpeg(locked_source, fps):
            yield chunk
            time.sleep(1.0 / fps)


def make_handler(service: AimingService):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, status, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/setup/preview.mjpg":
                if service.preview_status() == 503:
                    return self._send(json.dumps({"error": "camera busy"}), 503,
                                      "application/json")
                self.send_response(200)
                self.send_header("Content-Type",
                                 f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
                self.end_headers()
                try:
                    for chunk in service.mjpeg_frames():
                        self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return
            body, status, ctype = service.handle_get(self.path)
            self._send(body, status, ctype)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return self._send(json.dumps({"error": "bad json"}), 400, "application/json")
            body, status, ctype = service.handle_post(self.path, payload)
            self._send(body, status, ctype)

        def log_message(self, *args):
            pass

    return Handler


def serve(service: AimingService, port: int = 8080) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(service)).serve_forever()
