"""Tests for thingino/new-camera: create a camera on the server, save its
config, hand it to prepare-sd.

Runs the real script against a mock of POST /api/cameras/provision and a
stand-in prepare-sd that records its arguments. Nothing here reaches the real
server or a real disk.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "thingino" / "new-camera"
SECRET = "provision-secret-123"
TOKEN = "d" * 64


class MockServer:
    def __init__(self):
        self.requests: list[dict] = []
        self.status = 201

    def handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                srv.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                     "body": json.loads(raw)})
                if self.headers.get("Authorization") != f"Bearer {SECRET}":
                    code, body = 401, {"error": "unauthorized"}
                elif srv.status != 201:
                    code, body = srv.status, {"error": "provision failed"}
                else:
                    code, body = 201, {"camera_id": 12, "claim_code": "SUNSET-AAAA-BBBB",
                                       "device_token": TOKEN}
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return H


@pytest.fixture
def rig(tmp_path):
    srv = MockServer()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    fake_sd = tmp_path / "fake-prepare-sd"
    fake_sd.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >"$FAKE_SD_ARGS"\nexit "${FAKE_SD_EXIT:-0}"\n')
    fake_sd.chmod(0o755)
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"), "CRON_SECRET": SECRET,
           "SUNSET_CAMERAS_DIR": str(tmp_path / "cameras"),
           "NEW_CAMERA_PREPARE_SD": str(fake_sd), "FAKE_SD_ARGS": str(tmp_path / "sd-args")}
    yield srv, f"http://127.0.0.1:{httpd.server_address[1]}", env, tmp_path
    httpd.shutdown()


def run(rig, *args, **env_extra):
    _srv, base, env, _tmp = rig
    return subprocess.run([str(SCRIPT), "--api", base, *args], env={**env, **env_extra},
                          capture_output=True, text=True)


def sd_args(rig) -> list[str] | None:
    p = rig[3] / "sd-args"
    return p.read_text().splitlines() if p.exists() else None


def conf_values(path: Path) -> dict:
    return dict(re.findall(r'^([A-Z_]+)="(.*)"$', path.read_text(), re.M))


def test_creates_the_camera_saves_its_config_and_writes_the_card(rig):
    srv, base, _env, tmp = rig
    r = run(rig, "--label", "wyze-1", "--wifi-ssid", "Home Net", "--disk", "disk5", "wyze-cam-3")
    assert r.returncode == 0, r.stderr

    (req,) = srv.requests
    assert req["path"] == "/api/cameras/provision"
    assert req["body"]["device_class"] == "thingino-wyze-v3"
    assert req["body"]["label"] == "wyze-1"
    assert re.fullmatch(r"thingino-[0-9a-f]{12}", req["body"]["hardware_id"])

    folder = tmp / "cameras" / "12-wyze-1"
    conf = folder / "sunset-agent.conf"
    assert stat.S_IMODE(conf.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert conf_values(conf) == {
        "API_BASE": base, "CAMERA_ID": "12", "DEVICE_TOKEN": TOKEN,
        "CLAIM_CODE": "SUNSET-AAAA-BBBB", "CAMERA_MODEL": "wyze-v3",
        # The agent must send the id the camera was created with, or register is refused.
        "HARDWARE_ID": req["body"]["hardware_id"],
    }

    assert f"{base}/setup/SUNSET-AAAA-BBBB" in r.stdout
    assert f"{base}/setup/SUNSET-AAAA-BBBB" in (folder / "setup.txt").read_text()
    # Wi-Fi on the card means nobody is asked for a root password: one is made.
    passfile = folder / "rootpass.txt"
    password = passfile.read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{20}", password)
    assert stat.S_IMODE(passfile.stat().st_mode) == 0o600
    assert sd_args(rig) == ["--conf", str(conf), "--wifi-ssid", "Home Net",
                            "--root-pass-file", str(passfile), "--disk", "disk5", "wyze-cam-3"]

    # The provisioning secret is used once and kept nowhere; the token and the
    # root password aren't printed.
    for f in folder.iterdir():
        assert SECRET not in f.read_text()
    assert SECRET not in r.stdout + r.stderr
    assert TOKEN not in r.stdout + r.stderr
    assert password not in r.stdout + r.stderr


def test_a_second_card_for_the_same_camera_keeps_its_root_password(rig):
    _srv, _base, _env, tmp = rig
    assert run(rig, "--label", "c1", "--wifi-ssid", "Home", "wyze-cam-3").returncode == 0
    passfile = tmp / "cameras" / "12-c1" / "rootpass.txt"
    first = passfile.read_text()
    r = run(rig, "--from", str(passfile.parent), "--wifi-ssid", "Home", "wyze-cam-3")
    assert r.returncode == 0, r.stderr
    assert passfile.read_text() == first
    assert "--root-pass-file" in sd_args(rig)


def test_without_wifi_the_setup_page_asks_for_the_password_so_none_is_made(rig):
    assert run(rig, "--label", "c1", "wyze-cam-3").returncode == 0
    assert not (rig[3] / "cameras" / "12-c1" / "rootpass.txt").exists()
    assert "--root-pass-file" not in sd_args(rig)


def test_the_default_server_is_the_www_host():
    # The bare domain answers 307; curl here and on the camera doesn't follow it.
    assert re.search(r"^API=https://www\.sunrisesunset\.studio$", SCRIPT.read_text(), re.M)


def test_a_redirect_is_explained_and_creates_nothing(rig):
    srv, _base, _env, tmp = rig
    srv.status = 307
    r = run(rig, "wyze-cam-3")
    assert r.returncode != 0
    assert "redirect" in r.stderr and "www.sunrisesunset.studio" in r.stderr
    assert not (tmp / "cameras").exists() and sd_args(rig) is None


def test_needs_the_secret_before_it_asks_the_server_anything(rig):
    srv = rig[0]
    r = run(rig, "wyze-cam-3", CRON_SECRET="")
    assert r.returncode != 0
    assert "CRON_SECRET" in r.stderr
    assert srv.requests == [] and sd_args(rig) is None


def test_a_refusal_from_the_server_saves_nothing_and_writes_no_card(rig):
    srv, _base, _env, tmp = rig
    r = run(rig, "wyze-cam-3", CRON_SECRET="wrong")
    assert r.returncode != 0
    assert "HTTP 401" in r.stderr
    assert not (tmp / "cameras").exists()
    assert sd_args(rig) is None

    srv.status = 500
    r = run(rig, "wyze-cam-3")
    assert r.returncode != 0 and "HTTP 500" in r.stderr
    assert not (tmp / "cameras").exists()


def test_a_failed_card_keeps_the_camera_and_says_how_to_retry(rig):
    srv, _base, _env, tmp = rig
    r = run(rig, "--label", "c1", "wyze-cam-3", FAKE_SD_EXIT="1")
    assert r.returncode != 0
    folder = tmp / "cameras" / "12-c1"
    assert (folder / "sunset-agent.conf").exists()
    assert f'--from "{folder}"' in r.stderr

    # The retry creates nothing new on the server.
    r = run(rig, "--from", str(folder), "--disk", "disk6", "wyze-cam-3")
    assert r.returncode == 0, r.stderr
    assert len(srv.requests) == 1
    assert sd_args(rig) == ["--conf", str(folder / "sunset-agent.conf"), "--disk", "disk6", "wyze-cam-3"]
    assert "SUNSET-AAAA-BBBB" in r.stdout


def test_no_card_stops_after_saving(rig):
    r = run(rig, "--no-card", "--camera-model", "sonoff-cam-s2", "--label", "s2")
    assert r.returncode == 0, r.stderr
    assert (rig[3] / "cameras" / "12-s2" / "sunset-agent.conf").exists()
    assert sd_args(rig) is None
    assert rig[0].requests[0]["body"]["device_class"] == "thingino-sonoff-cam-s2"


def test_an_already_flashed_camera_gets_an_agent_only_card(rig):
    r = run(rig, "--fat32", "--camera-model", "wyze-v3", "--label", "pan")
    assert r.returncode == 0, r.stderr
    assert sd_args(rig) == ["--conf", str(rig[3] / "cameras" / "12-pan" / "sunset-agent.conf"), "--fat32"]


@pytest.mark.parametrize("args, message", [
    (["some-unknown-installer"], "--camera-model"),          # can't guess which camera
    (["--fat32"], "--camera-model"),
    (["--label", "bad label", "wyze-cam-3"], "--label"),
    (["--label", 'x","label":"y', "wyze-cam-3"], "--label"),  # can't break out of the JSON
    (["--from", "/nonexistent", "wyze-cam-3"], "no sunset-agent.conf"),
    (["--fat32", "wyze-cam-3"], "--fat32"),
])
def test_bad_arguments_stop_before_anything_is_created(rig, args, message):
    r = run(rig, *args)
    assert r.returncode != 0
    assert message in r.stderr
    assert rig[0].requests == [] and sd_args(rig) is None
