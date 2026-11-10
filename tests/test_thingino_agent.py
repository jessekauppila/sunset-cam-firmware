"""End-to-end tests for thingino/sunset-agent (the shell agent for Thingino cameras).

Runs the real script under dash (close to busybox ash) against a mock of the
parent app's camera endpoints. Needs `dash` and Thingino's `jct` JSON tool on
PATH (build it from https://github.com/themactep/jct with `make`); skipped
otherwise. The sun-math check additionally needs `astral` (skipped if absent).
"""

from __future__ import annotations

import datetime as dt
from email.parser import BytesParser
from email.policy import HTTP
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parent.parent / "thingino" / "sunset-agent"

pytestmark = pytest.mark.skipif(
    not (shutil.which("dash") and shutil.which("jct")),
    reason="needs dash and jct on PATH",
)

TOKEN = "t" * 64


class MockApp:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.aimed = False
        self.previews_wanted = 0  # preview frames still wanted by a (pretend) open wizard
        self.register_replies: list[int] = []  # HTTP statuses for the next register calls, then 200

    def handler(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                auth = self.headers.get("Authorization")
                if self.path == "/api/cameras/register":
                    app.calls.append(("register", json.loads(raw)))
                    if app.register_replies:
                        return self._json(app.register_replies.pop(0), {"error": "not now"})
                    return self._json(200, {"camera_id": 7, "placement_status": "awaiting_aim"})
                if auth != f"Bearer {TOKEN}":
                    return self._json(401, {"error": "unauthorized"})
                if self.path == "/api/cameras/7/preview":
                    app.calls.append(("preview", {"bytes": n, "jpeg": b"\xff\xd8\xff" in raw}))
                    app.previews_wanted -= 1
                    return self._json(200, {"preview_wanted": app.previews_wanted > 0})
                if self.path == "/api/cameras/7/heartbeat":
                    app.calls.append(("heartbeat", json.loads(raw)))
                    if not app.aimed:
                        # Neon serializes NUMERIC as strings; mimic that.
                        body = {"acknowledged_at": "x", "placement_status": "awaiting_aim",
                                "lat": "48.750000", "lng": "-122.480000"}
                        if app.previews_wanted > 0:
                            body["preview_wanted"] = True
                        return self._json(200, body)
                    return self._json(200, {"acknowledged_at": "x", "placement_status": "ready",
                                            "placement": {"lat": "48.750000", "lng": "-122.480000",
                                                          "phase_preference": "sunset"}})
                if self.path == "/api/cameras/7/placement":
                    body = json.loads(raw)
                    app.calls.append(("placement", body))
                    app.aimed = True
                    return self._json(200, {"placement_status": "ready"})
                if self.path == "/api/cameras/7/snapshot":
                    msg = BytesParser(policy=HTTP).parsebytes(
                        f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + raw
                    )
                    fields = {}
                    for part in msg.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        payload = part.get_payload(decode=True)
                        if name == "image":
                            fields["image_bytes"] = len(payload)
                        else:
                            fields[name] = payload.decode()
                    app.calls.append(("snapshot", fields))
                    return self._json(202, {"snapshot_id": 1, "accepted_at": "x"})
                return self._json(404, {"error": "nope"})

        return H


@pytest.fixture
def server():
    app = MockApp()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _write_conf(tmp_path: Path, base: str, **extra) -> Path:
    jpeg = tmp_path / "frame.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 2000 + b"\xff\xd9")
    conf = {
        "API_BASE": base,
        "CAMERA_ID": "7",
        "DEVICE_TOKEN": TOKEN,
        "CLAIM_CODE": "SUNSET-TEST-0001",
        "HARDWARE_ID": "thingino-test",
        "CAMERA_MODEL": "wyze-v3",
        "AZIMUTH_DEG": "265",
        "TILT_DEG": "3",
        "INTERVAL_S": "1",
        # A day-wide window so the test is always "inside" one.
        "SUNSET_BEFORE_MIN": "1440",
        "SUNSET_AFTER_MIN": "1440",
        "SNAPSHOT_CMD": f"cat {jpeg}",
    }
    conf.update(extra)
    path = tmp_path / "sunset-agent.conf"
    path.write_text("".join(f'{k}="{v}"\n' for k, v in conf.items()))
    return path


def _env(tmp_path, conf):
    return {**os.environ, "SUNSET_CONF": str(conf), "SUNSET_STATE_DIR": str(tmp_path / "state")}


def test_onboarding_then_capture(server, tmp_path):
    app, base = server
    conf = _write_conf(tmp_path, base)
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 20
    while time.time() < deadline and sum(1 for c in app.calls if c[0] == "snapshot") < 2:
        time.sleep(0.2)
    proc.terminate()
    proc.wait(5)

    kinds = [c[0] for c in app.calls]
    assert kinds[0] == "register"
    assert app.calls[0][1]["hardware_id"] == "thingino-test"
    assert app.calls[0][1]["capabilities"]["camera_model"] == "wyze-v3"
    assert ("placement", {"azimuth_deg": 265, "tilt_deg": 3}) in app.calls
    # No frame may go up before placement is ready.
    assert kinds.index("snapshot") > kinds.index("placement")
    snaps = [c[1] for c in app.calls if c[0] == "snapshot"]
    assert snaps[0]["phase"] == "sunset"
    assert snaps[0]["window_id"].endswith("-sunset-cam7")
    assert [s["frame_seq"] for s in snaps[:2]] == ["1", "2"]
    assert snaps[0]["image_bytes"] > 2000
    dt.datetime.fromisoformat(snaps[0]["captured_at"].replace("Z", "+00:00"))


def test_waits_for_aim_when_none_configured(server, tmp_path):
    app, base = server
    conf = _write_conf(tmp_path, base, AZIMUTH_DEG="", TILT_DEG="")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    time.sleep(3)
    proc.terminate()
    proc.wait(5)
    kinds = [c[0] for c in app.calls]
    assert "heartbeat" in kinds
    assert "snapshot" not in kinds


def test_sends_setup_previews_while_the_wizard_watches(server, tmp_path):
    app, base = server
    app.previews_wanted = 3
    jpeg = tmp_path / "small.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"p" * 500 + b"\xff\xd9")
    conf = _write_conf(tmp_path, base, AZIMUTH_DEG="", TILT_DEG="",
                       PREVIEW_CMD=f"cat {jpeg}", PREVIEW_INTERVAL_S="0")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    while time.time() < deadline and [c[0] for c in app.calls].count("heartbeat") < 2:
        time.sleep(0.2)
    proc.terminate()
    proc.wait(5)

    kinds = [c[0] for c in app.calls]
    assert app.calls[0][1]["capabilities"]["preview"] is True
    previews = [c[1] for c in app.calls if c[0] == "preview"]
    assert len(previews) == 3  # stops as soon as the server says nobody is watching
    assert all(p["jpeg"] for p in previews)
    assert "snapshot" not in kinds  # previews are never captures
    # Heartbeats again right after the session ends (the aim may have arrived).
    assert kinds.index("heartbeat", kinds.index("preview")) > kinds.index("preview")


def _kinds(app):
    return [c[0] for c in app.calls]


def test_keeps_registering_until_the_server_answers(server, tmp_path):
    """A setup card starts the agent before the camera has Wi-Fi. Registration
    carries the model and capabilities the wizard needs, so it must be retried."""
    app, base = server
    app.aimed = True
    app.register_replies = [503, 503]
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 20
    while time.time() < deadline and _kinds(app).count("heartbeat") < 5:
        time.sleep(0.2)
    proc.terminate()
    proc.wait(5)
    # Two refusals, one success, then no more: it doesn't re-register every heartbeat.
    assert _kinds(app).count("register") == 3
    assert _kinds(app).count("heartbeat") >= 5


def test_stops_registering_when_the_server_refuses_the_claim(server, tmp_path):
    app, base = server
    app.aimed = True
    app.register_replies = [409]  # hardware id mismatch: retrying can't fix it
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline and _kinds(app).count("heartbeat") < 3:
        time.sleep(0.2)
    proc.terminate()
    proc.wait(5)
    assert _kinds(app).count("register") == 1
    assert _kinds(app).count("heartbeat") >= 3


def test_sun_windows_match_astral(tmp_path):
    astral = pytest.importorskip("astral")
    from astral.sun import sunrise, sunset

    places = [(48.75, -122.48), (35.68, 139.69), (-33.87, 151.21), (64.15, -21.94),
              (-0.18, -78.47), (-18.1, 178.4), (-13.8, -171.8)]
    days = [dt.date(2026, 1, 15), dt.date(2026, 3, 20), dt.date(2026, 6, 21), dt.date(2026, 12, 21)]
    env = {**os.environ, "SUNSET_CONF": "/nonexistent", "SUNSET_STATE_DIR": str(tmp_path),
           "SUNSET_AGENT_LIB": "1"}
    for lat, lng in places:
        obs = astral.Observer(lat, lng)
        for day in days:
            noon = int(dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.timezone.utc).timestamp())
            out = subprocess.run(["dash", "-c", f". {AGENT}; windows {noon} {lat} {lng} both list"],
                                 env=env, capture_output=True, text=True, check=True).stdout
            assert out.strip(), (lat, lng, day)
            for line in out.splitlines():
                phase, _wid, _st, ev, _en = line.split()
                got = dt.datetime.fromisoformat(ev.split("=")[1].replace("Z", "+00:00"))
                fn = sunrise if phase == "sunrise" else sunset
                refs = [fn(obs, day + dt.timedelta(days=k)) for k in (-1, 0, 1)]
                err_min = min(abs((got - r).total_seconds()) for r in refs) / 60
                assert err_min < 3, (lat, lng, day, phase, got, err_min)
