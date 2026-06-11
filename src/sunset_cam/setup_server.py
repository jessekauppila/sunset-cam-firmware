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

import os
from urllib.parse import urlparse, parse_qs

from sunset_cam.heading import HeadingState, heading_from_tap
from sunset_cam.solstice_math import (
    compute_sun_azimuth, fov_fit, sunset_arc_azimuths, sunrise_arc_azimuths,
)
from sunset_cam.setup_alignment import render_align_page, stream_mjpeg, MJPEG_BOUNDARY
from sunset_cam.sun_detect import detect_sun_centroid


DEFAULT_PLACEMENT_PATH = "/etc/sunset-cam/placement.json"


def _default_placement_sink(placement: dict) -> None:
    os.makedirs(os.path.dirname(DEFAULT_PLACEMENT_PATH), exist_ok=True)
    with open(DEFAULT_PLACEMENT_PATH, "w") as f:
        json.dump(placement, f)


class AimingService:
    def __init__(
        self, *, lat: float, lng: float, phase: str, hfov_deg: float, width: int,
        frame_source: Callable[[], bytes],
        reader: "Callable[[], tuple[float, float]] | None" = None,
        now_utc_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        placement_sink: Callable[[dict], None] = _default_placement_sink,
        mount_roll_ref_deg: float = 0.0, mount_pitch_ref_deg: float = 0.0,
        level_tol_deg: float = 5.0,
        sun_source: Callable[[], "object | None"] | None = None,
        static_dir: "str | None" = None,
    ) -> None:
        self.lat, self.lng, self.phase = lat, lng, phase
        self.hfov_deg, self.width = hfov_deg, width
        self.frame_source = frame_source
        self.reader = reader
        self.now_utc_fn = now_utc_fn
        self.placement_sink = placement_sink
        self.mount_roll_ref_deg = mount_roll_ref_deg
        self.mount_pitch_ref_deg = mount_pitch_ref_deg
        self.level_tol_deg = level_tol_deg
        # Optional live sun source (grayscale array | None) for auto-track aiming.
        self.sun_source = sun_source
        # Tilt the mated phone measured (used when there's no on-device MPU).
        self._supplied_orientation: "tuple[float, float] | None" = None
        # If set, serve the setup-wizard static bundle from this dir at "/".
        self.static_dir = static_dir
        # How the current heading was set ("sun" | "phone" | "window" | "manual").
        self._aim_source: "str | None" = None
        self.state = HeadingState(
            hfov_deg=hfov_deg, width=width, level_tol_deg=level_tol_deg,
            mount_roll_ref_deg=mount_roll_ref_deg, mount_pitch_ref_deg=mount_pitch_ref_deg,
        )
        self._cam_lock = threading.Lock()

    def _orientation(self) -> tuple[float, float]:
        # MPU is optional. With no IMU (or a transient read error) assume the camera
        # sits at its mount reference — the install was verified another way (phone),
        # so the on-device level gate should pass rather than block aiming.
        if self.reader is None:
            # no on-device IMU: prefer the mated phone's reported tilt, else assume level
            return self._supplied_orientation or (self.mount_roll_ref_deg, self.mount_pitch_ref_deg)
        try:
            return self.reader()
        except Exception:
            return (self.mount_roll_ref_deg, self.mount_pitch_ref_deg)

    def _is_level(self, roll: float, pitch: float) -> bool:
        return (abs(roll - self.mount_roll_ref_deg) <= self.level_tol_deg
                and abs(pitch - self.mount_pitch_ref_deg) <= self.level_tol_deg)

    def _track_sun(self, roll: float, pitch: float):
        """Live heading from the detected sun, or None. Returns
        (heading_deg, sun_fx, sun_fy) where the fractions are 0..1 across the frame."""
        if self.sun_source is None or not self._is_level(roll, pitch):
            return None
        with self._cam_lock:          # share the camera with the MJPEG preview
            frame = self.sun_source()
        if frame is None:
            return None
        c = detect_sun_centroid(frame)
        if c is None:
            return None
        cx, cy = c
        fh, fw = frame.shape[0], frame.shape[1]
        sun_az = compute_sun_azimuth(self.lat, self.lng, self.now_utc_fn())
        # cx is in this frame's pixel space; heading_from_tap only uses cx/width.
        heading = heading_from_tap(sun_az, cx, fw, self.hfov_deg)
        return heading, cx / fw, cy / fh

    def _current_aim(self, roll: float, pitch: float):
        """(status, heading|None, sun_fxy|None). Auto-track wins when the sun is
        detected; otherwise fall back to the manual tap state."""
        track = self._track_sun(roll, pitch)
        if track is not None:
            heading, fx, fy = track
            return "tracking", heading, (fx, fy)
        self.state.update_orientation(roll, pitch)
        return self.state.status(), self.state.heading_deg(), None

    def _fit_payload(self) -> dict:
        roll, pitch = self._orientation()
        status, heading, sun = self._current_aim(roll, pitch)
        payload = {"status": status, "roll_deg": roll, "pitch_deg": pitch,
                   "has_mpu": self.reader is not None}
        if sun is not None:
            payload["sun_fx"], payload["sun_fy"] = sun
        if heading is not None:
            year = self.now_utc_fn().year
            fit = fov_fit(self.lat, self.lng, heading, self.hfov_deg, year)
            payload.update({"heading_deg": heading, **fit})
        return payload

    _STATIC_FILES = {"/", "/index.html", "/wizard.css", "/wizard.js", "/api.js"}
    _CTYPES = {"html": "text/html; charset=utf-8", "css": "text/css",
               "js": "text/javascript", "json": "application/json"}

    def _static(self, route: str):
        name = "index.html" if route in ("/", "/index.html") else route.lstrip("/")
        ext = name.rsplit(".", 1)[-1]
        with open(os.path.join(self.static_dir, name)) as f:
            return f.read(), 200, self._CTYPES.get(ext, "application/octet-stream")

    def _arc_azimuths(self, facing: str):
        year = self.now_utc_fn().year
        jun, equinox, dec = (sunrise_arc_azimuths if facing == "east"
                             else sunset_arc_azimuths)(self.lat, year)
        today = compute_sun_azimuth(self.lat, self.lng, self.now_utc_fn())
        return (json.dumps({"jun": jun, "equinox": equinox, "dec": dec, "today": today}),
                200, "application/json")

    def handle_get(self, path: str):
        route = path.split("?", 1)[0]
        # the setup-wizard bundle (when deployed) is served at "/"; falls back to
        # the legacy render_align_page when no static bundle is configured.
        if self.static_dir and route in self._STATIC_FILES:
            return self._static(route)
        if route in ("/", "/setup/align"):
            return (render_align_page(
                self.lat, self.lng, phase=self.phase,
                mount_roll_ref_deg=self.mount_roll_ref_deg,
                mount_pitch_ref_deg=self.mount_pitch_ref_deg,
                level_tol_deg=self.level_tol_deg,
                hfov_deg=self.hfov_deg,
            ), 200, "text/html; charset=utf-8")
        if route == "/setup/orientation.json":
            roll, pitch = self._orientation()
            return json.dumps({"roll_deg": roll, "pitch_deg": pitch}), 200, "application/json"
        if route == "/setup/state.json":
            return json.dumps(self._fit_payload()), 200, "application/json"
        if route == "/setup/arc-azimuths":
            facing = parse_qs(urlparse(path).query).get("facing", ["west"])[0]
            return self._arc_azimuths(facing)
        return json.dumps({"error": "not found"}), 404, "application/json"

    def handle_post(self, path: str, body: dict):
        if path == "/setup/tap":
            roll, pitch = self._orientation()
            sun_az = compute_sun_azimuth(self.lat, self.lng, self.now_utc_fn())
            # accept a fraction (fx, 0..1, the wizard's native unit) or a raw pixel_x
            px = float(body["fx"]) * self.width if "fx" in body else float(body["pixel_x"])
            ok = self.state.apply_tap(sun_az, px, roll, pitch)
            if ok:
                self._aim_source = "sun"
            if not ok:
                return (json.dumps({"status": "uncalibrated", "error": "level the camera first"}),
                        422, "application/json")
            return json.dumps(self._fit_payload()), 200, "application/json"
        if path == "/setup/heading":
            # direct heading from a non-sun source (phone compass / manual dial)
            if "roll_deg" in body and "pitch_deg" in body:
                # the mated phone reported the camera's tilt — use it when there's no MPU
                self._supplied_orientation = (float(body["roll_deg"]), float(body["pitch_deg"]))
            roll, pitch = self._orientation()
            ok = self.state.apply_heading(float(body["heading_deg"]), roll, pitch)
            if ok:
                self._aim_source = body.get("source", "manual")
            if not ok:
                return (json.dumps({"status": "uncalibrated",
                                    "error": "level the camera first"}),
                        422, "application/json")
            return json.dumps(self._fit_payload()), 200, "application/json"
        if path == "/setup/confirm":
            roll, pitch = self._orientation()
            status, heading, _ = self._current_aim(roll, pitch)
            if status not in ("tracking", "tapped") or heading is None:
                return (json.dumps({"status": status,
                                    "error": "aim not set — tap the sun first"}),
                        409, "application/json")
            # live sun-tracking is precise; a latched tap is "sun"; else the set source
            source = "sun" if status == "tracking" else (self._aim_source or "sun")
            placement = {
                "azimuth_deg": heading,
                "tilt_deg": pitch,
                "roll_deg": roll,
                "source": source,
                "coarse": source != "sun",   # phone/window/manual → eligible for sun refine
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
