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
        self.rotation = None  # placement.bracket.image_rotation_deg; None = the wizard never asked
        self.next_windows = None  # the ready reply's next_windows; None = key absent (server doesn't say)
        self.heartbeat_down = False  # answer heartbeats with 500, as if unreachable

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

            def _multipart(self, raw):
                msg = BytesParser(policy=HTTP).parsebytes(
                    f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + raw
                )
                fields = {}
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    payload = part.get_payload(decode=True)
                    fields[name] = payload if name == "image" else payload.decode()
                return fields

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                auth = self.headers.get("Authorization")
                if self.path == "/api/cameras/register":
                    app.calls.append(("register", json.loads(raw)))
                    return self._json(200, {"camera_id": 7, "placement_status": "awaiting_aim"})
                if auth != f"Bearer {TOKEN}":
                    return self._json(401, {"error": "unauthorized"})
                if self.path == "/api/cameras/7/preview":
                    app.calls.append(("preview", {"bytes": n, "jpeg": b"\xff\xd8\xff" in raw,
                                                  "rotation_deg": self._multipart(raw).get("rotation_deg")}))
                    app.previews_wanted -= 1
                    return self._json(200, {"preview_wanted": app.previews_wanted > 0})
                if self.path == "/api/cameras/7/heartbeat":
                    app.calls.append(("heartbeat", json.loads(raw)))
                    if app.heartbeat_down:
                        return self._json(500, {"error": "down"})
                    if not app.aimed:
                        # Neon serializes NUMERIC as strings; mimic that.
                        body = {"acknowledged_at": "x", "placement_status": "awaiting_aim",
                                "lat": "48.750000", "lng": "-122.480000"}
                        if app.previews_wanted > 0:
                            body["preview_wanted"] = True
                        return self._json(200, body)
                    placement = {"lat": "48.750000", "lng": "-122.480000", "phase_preference": "sunset"}
                    if app.rotation is not None:
                        placement["bracket"] = {"lens": "fixed", "image_rotation_deg": app.rotation}
                    reply = {"acknowledged_at": "x", "placement_status": "ready", "placement": placement}
                    if app.next_windows is not None:
                        reply["next_windows"] = app.next_windows
                    return self._json(200, reply)
                if self.path == "/api/cameras/7/placement":
                    body = json.loads(raw)
                    app.calls.append(("placement", body))
                    app.aimed = True
                    return self._json(200, {"placement_status": "ready"})
                if self.path == "/api/cameras/7/snapshot":
                    fields = self._multipart(raw)
                    fields["image_bytes"] = len(fields.pop("image"))
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
        "IDLE_SLEEP_S": "1",
        # A day-wide window so the test is always "inside" one.
        "SUNSET_BEFORE_MIN": "1440",
        "SUNSET_AFTER_MIN": "1440",
        "SNAPSHOT_CMD": f"cat {jpeg}",
        # No prudynt on the test machine: record flips instead (see _flip_log).
        "FLIP_CMD": f"sh {_fake_flip(tmp_path)}",
        "FLIP_STATE_CMD": "echo 0",
    }
    conf.update(extra)
    path = tmp_path / "sunset-agent.conf"
    path.write_text("".join(f'{k}="{v}"\n' for k, v in conf.items()))
    return path


def _fake_flip(tmp_path: Path) -> Path:
    """A stand-in FLIP_CMD: appends its argument (true|false) to flip.log."""
    script = tmp_path / "fake-flip"
    script.write_text(f'echo "$1" >> {tmp_path / "flip.log"}\n')
    return script


def _flip_log(tmp_path: Path) -> list[str]:
    log = tmp_path / "flip.log"
    return log.read_text().split() if log.exists() else []


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


def _run_until(app, proc, done, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline and not done():
        time.sleep(0.2)
    proc.terminate()
    proc.wait(5)


def test_turns_the_picture_over_when_mounted_upside_down(server, tmp_path):
    app, base = server
    app.aimed = True
    app.rotation = 180
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    # Several heartbeats all say 180, then the camera is re-aimed the right way up.
    heartbeats = lambda: [c[0] for c in app.calls].count("heartbeat")  # noqa: E731
    deadline = time.time() + 15
    while time.time() < deadline and heartbeats() < 3:
        time.sleep(0.2)
    app.rotation = 0
    seen = heartbeats()
    _run_until(app, proc, lambda: heartbeats() >= seen + 2)

    assert app.calls[0][1]["capabilities"]["image_flip"] is True
    # Flipped once (not on every heartbeat), then flipped back.
    assert _flip_log(tmp_path) == ["true", "false"]


def test_leaves_the_flip_alone_when_the_wizard_never_asked(server, tmp_path):
    app, base = server
    app.aimed = True  # ready placement, but no bracket.image_rotation_deg
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    _run_until(app, proc, lambda: [c[0] for c in app.calls].count("heartbeat") >= 3)
    assert [c[0] for c in app.calls].count("heartbeat") >= 3
    assert _flip_log(tmp_path) == []


def test_retries_a_flip_that_failed(server, tmp_path):
    app, base = server
    app.aimed = True
    app.rotation = 180
    # Fails the first time it runs, works after that.
    flaky = tmp_path / "flaky-flip"
    flaky.write_text(
        f'echo "$1" >> {tmp_path / "flip.log"}\n'
        f'[ -f {tmp_path / "tried"} ] || {{ touch {tmp_path / "tried"}; exit 1; }}\n'
    )
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1", FLIP_CMD=f"sh {flaky}")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    _run_until(app, proc, lambda: [c[0] for c in app.calls].count("heartbeat") >= 4)
    assert _flip_log(tmp_path) == ["true", "true"]  # second try stuck; no third


def test_says_it_cannot_flip_when_flip_is_turned_off(server, tmp_path):
    app, base = server
    app.aimed = True
    app.rotation = 180
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1", FLIP_CMD="")
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    _run_until(app, proc, lambda: [c[0] for c in app.calls].count("heartbeat") >= 2)
    assert app.calls[0][1]["capabilities"]["image_flip"] is False
    assert _flip_log(tmp_path) == []


@pytest.mark.parametrize("state_cmd, expected", [("echo 0", "0"), ("echo 180", "180"), ("false", "0")])
def test_preview_frames_say_what_flip_the_camera_applied(server, tmp_path, state_cmd, expected):
    app, base = server
    app.previews_wanted = 2
    jpeg = tmp_path / "small.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"p" * 500 + b"\xff\xd9")
    conf = _write_conf(tmp_path, base, AZIMUTH_DEG="", TILT_DEG="", PREVIEW_CMD=f"cat {jpeg}",
                       PREVIEW_INTERVAL_S="0", FLIP_STATE_CMD=state_cmd)
    proc = subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)
    _run_until(app, proc, lambda: [c[0] for c in app.calls].count("preview") >= 2, timeout=10)
    previews = [c[1] for c in app.calls if c[0] == "preview"]
    assert len(previews) == 2
    assert {p["rotation_deg"] for p in previews} == {expected}


FAKE_PRUDYNTCTL = r"""#!/bin/sh
# Stand-in for Thingino's prudyntctl: keeps the flip in $FAKE_DIR/flip and
# answers like the real one (exit 0 whether or not the request was accepted).
state="$FAKE_DIR/flip"
[ -f "$state" ] || echo false >"$state"
case "$1" in
json)
	if [ "$2" = - ]; then body=$(cat); else body=$2; fi
	if [ ! -f "$FAKE_DIR/refuse" ]; then
		case "$body" in
		*'"hflip":true,"vflip":true'*) echo true >"$state" ;;
		*'"hflip":false,"vflip":false'*) echo false >"$state" ;;
		esac
	fi
	v=$(cat "$state")
	printf '{"image":{"vflip":%s,"hflip":%s}}\n' "$v" "$v"
	;;
snapshot) echo "snapshot $2 $3" >>"$FAKE_DIR/calls" ;;
esac
exit 0
"""


def _fake_prudynt(tmp_path: Path, *, layered: bool) -> dict:
    """PATH with a fake prudyntctl, and either prudynt-config (current builds) or
    only a jct that accepts `set` (builds before the layered config)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "prudyntctl").write_text(FAKE_PRUDYNTCTL)
    if layered:
        (bin_dir / "prudynt-config").write_text('#!/bin/sh\necho "$*" >>"$FAKE_DIR/stored"\n')
    real_jct = shutil.which("jct")
    (bin_dir / "jct").write_text(
        f'#!/bin/sh\n[ "$2" = set ] && {{ echo "$*" >>"$FAKE_DIR/stored"; exit 0; }}\nexec {real_jct} "$@"\n'
    )
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_DIR": str(tmp_path),
            "SUNSET_CONF": "/nonexistent", "SUNSET_STATE_DIR": str(tmp_path / "state"),
            "SUNSET_AGENT_LIB": "1"}


def _lib(env, script):
    return subprocess.run(["dash", "-c", f". {AGENT}; {script}"], env=env,
                          capture_output=True, text=True)


def _stored(tmp_path: Path) -> list[str]:
    f = tmp_path / "stored"
    return f.read_text().splitlines() if f.exists() else []


def test_default_flip_drives_prudynt_and_stores_the_setting(tmp_path):
    env = _fake_prudynt(tmp_path, layered=True)
    out = _lib(env, "current_rotation; echo; set_rotation 180; current_rotation; echo; "
                    "set_rotation 0; current_rotation; echo; capabilities_json")
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines[:3] == ["0", "180", "0"]
    assert json.loads(lines[3])["image_flip"] is True
    assert _stored(tmp_path) == ["set image.hflip true", "set image.vflip true",
                                 "set image.hflip false", "set image.vflip false"]
    # One frame per stream is thrown away after each flip (it may predate the flip).
    assert (tmp_path / "calls").read_text().splitlines() == ["snapshot -c 0", "snapshot -c 1"] * 2


def test_default_flip_stores_through_jct_on_builds_without_prudynt_config(tmp_path):
    env = _fake_prudynt(tmp_path, layered=False)
    out = _lib(env, "set_rotation 180; current_rotation")
    assert out.stdout.strip() == "180", out.stderr
    assert _stored(tmp_path) == ["/etc/prudynt.json set image.hflip true",
                                 "/etc/prudynt.json set image.vflip true"]


def test_default_flip_notices_when_the_streamer_refuses(tmp_path):
    env = _fake_prudynt(tmp_path, layered=True)
    (tmp_path / "refuse").touch()  # prudyntctl still exits 0, as the real one does
    out = _lib(env, 'set_rotation 180; echo "rc=$? applied=$IMAGE_ROTATION"; current_rotation')
    assert out.stdout.splitlines() == ["rc=1 applied=", "0"]
    assert "will retry" in out.stderr
    assert _stored(tmp_path) == []


def test_does_not_claim_flip_without_prudynt(tmp_path):
    env = _fake_prudynt(tmp_path, layered=True)
    (tmp_path / "bin" / "prudyntctl").unlink()
    out = _lib(env, "capabilities_json; set_rotation 180; echo; echo rc=$?")
    assert json.loads(out.stdout.splitlines()[0])["image_flip"] is False
    assert out.stdout.splitlines()[-1] == "rc=0"  # nothing to do, not an error


def _iso(offset_s: float) -> str:
    """A UTC timestamp the way the server writes them (JS toISOString)."""
    t = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset_s)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _window(phase, window_id, start_s, end_s):
    return {"phase": phase, "window_id": window_id, "start_at": _iso(start_s),
            "event_at": _iso((start_s + end_s) / 2), "end_at": _iso(end_s)}


def _snapshots(app):
    return [c[1] for c in app.calls if c[0] == "snapshot"]


def _agent(tmp_path, conf):
    return subprocess.Popen(["dash", str(AGENT), "run"], env=_env(tmp_path, conf),
                            stderr=subprocess.DEVNULL)


def _stop(proc):
    proc.terminate()
    proc.wait(5)


def _wait(done, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline and not done():
        time.sleep(0.2)
    return done()


def _heartbeats(app):
    return [c[0] for c in app.calls].count("heartbeat")


def test_follows_the_servers_window_and_uses_its_id(server, tmp_path):
    app, base = server
    app.aimed = True
    # A sunrise window, on a camera configured for sunsets, with no window of its
    # own open (zero-length): everything about the capture must come from the server.
    app.next_windows = [_window("sunrise", "2026-11-08-sunrise-cam7", -600, 600),
                        _window("sunset", "2026-11-08-sunset-cam7", 30000, 34500)]
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1", SUNSET_BEFORE_MIN="0", SUNSET_AFTER_MIN="0")
    proc = _agent(tmp_path, conf)
    assert _wait(lambda: len(_snapshots(app)) >= 2)
    _stop(proc)
    snaps = _snapshots(app)
    assert {s["window_id"] for s in snaps} == {"2026-11-08-sunrise-cam7"}
    assert {s["phase"] for s in snaps} == {"sunrise"}
    assert [s["frame_seq"] for s in snaps[:2]] == ["1", "2"]


@pytest.mark.parametrize("windows", [
    [],                                                        # paused, or polar night
    [("sunset", "2026-11-09-sunset-cam7", 3600, 8100)],        # next one is an hour away
    [("sunset", "2026-11-07-sunset-cam7", -8100, -3600)],      # only a finished one
])
def test_captures_nothing_outside_the_servers_windows(server, tmp_path, windows):
    """The camera's own maths says a window is open (the test config's are a day
    wide). The server's list wins."""
    app, base = server
    app.aimed = True
    app.next_windows = [_window(*w) for w in windows]
    proc = _agent(tmp_path, _write_conf(tmp_path, base, HEARTBEAT_S="1"))
    assert _wait(lambda: _heartbeats(app) >= 4)
    _stop(proc)
    assert _snapshots(app) == []


def test_works_windows_out_itself_when_the_server_does_not_say(server, tmp_path):
    app, base = server
    app.aimed = True
    app.next_windows = []          # the server says: nothing
    proc = _agent(tmp_path, _write_conf(tmp_path, base, HEARTBEAT_S="1"))
    assert _wait(lambda: _heartbeats(app) >= 3)
    assert _snapshots(app) == []
    app.next_windows = None        # then stops saying (an older server, say)
    assert _wait(lambda: len(_snapshots(app)) >= 1)
    _stop(proc)
    assert _snapshots(app)[0]["window_id"].endswith("-sunset-cam7")  # its own id


def test_keeps_the_servers_list_through_an_outage_then_falls_back(server, tmp_path):
    app, base = server
    app.aimed = True
    app.next_windows = []
    conf = _write_conf(tmp_path, base, HEARTBEAT_S="1", SERVER_WINDOWS_MAX_AGE_S="4")
    proc = _agent(tmp_path, conf)
    assert _wait(lambda: _heartbeats(app) >= 2)
    app.heartbeat_down = True
    went_down = time.time()
    assert _wait(lambda: len(_snapshots(app)) >= 1, timeout=20)
    _stop(proc)
    # It obeyed the last list ("nothing") for a while after losing the server,
    # and only then went back to its own windows.
    assert time.time() - went_down >= 2
    assert _snapshots(app)[0]["window_id"].endswith("-sunset-cam7")


def test_ignores_window_entries_it_cannot_trust(server, tmp_path):
    app, base = server
    app.aimed = True
    good = _window("sunset", "2026-11-08-sunset-cam7", -600, 600)
    app.next_windows = [
        _window("sunset", "@/etc/passwd", -600, 600),               # would be read as a file by curl -F
        _window("sunset", "id;type=text/html", -600, 600),
        _window("noon", "2026-11-08-noon-cam7", -600, 600),
        {**good, "window_id": "2026-11-08-local-cam7", "start_at": "2026-11-08T16:00:00-08:00"},  # not UTC
        good,
    ]
    proc = _agent(tmp_path, _write_conf(tmp_path, base, HEARTBEAT_S="1"))
    assert _wait(lambda: len(_snapshots(app)) >= 2)
    _stop(proc)
    assert {s["window_id"] for s in _snapshots(app)} == {"2026-11-08-sunset-cam7"}


def test_reads_the_servers_timestamps(tmp_path):
    env = {**os.environ, "SUNSET_CONF": "/nonexistent", "SUNSET_STATE_DIR": str(tmp_path),
           "SUNSET_AGENT_LIB": "1"}

    def epoch(s):
        return subprocess.run(["dash", "-c", f". {AGENT}; iso_epoch '{s}'"], env=env,
                              capture_output=True, text=True, check=True).stdout

    for stamp in ["2026-11-09T00:09:43.000Z", "2026-11-09T00:09:43Z", "1970-01-01T00:00:00Z",
                  "2028-02-29T23:59:59.500Z", "2100-03-01T12:00:00Z"]:
        want = int(dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
        assert epoch(stamp) == str(want), stamp
    for bad in ["", "2026-11-09", "2026-11-09T00:09:43", "2026-11-09T00:09:43+01:00", "tomorrow"]:
        assert epoch(bad) == "", bad


def test_default_padding_matches_the_servers(tmp_path):
    """Sunrise 45 before / 30 after, sunset 30 before / 45 after (device-protocol §9.1)."""
    env = {**os.environ, "SUNSET_CONF": "/nonexistent", "SUNSET_STATE_DIR": str(tmp_path),
           "SUNSET_AGENT_LIB": "1"}
    out = subprocess.run(
        ["dash", "-c", f'. {AGENT}; echo "$SUNRISE_BEFORE_MIN $SUNRISE_AFTER_MIN $SUNSET_BEFORE_MIN $SUNSET_AFTER_MIN"'],
        env=env, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["45", "30", "30", "45"]


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
