"""Smoke tests for the production entrypoints systemd actually runs.

Background: camera 2 sat dark for ~3 hours because `boot.py` had no
`if __name__ == "__main__": main()` guard, so `python -m sunset_cam.boot`
imported and exited without running anything. That was one instance of a class:
the path systemd runs (`python -m pkg.mod` -> `main()` -> real config + IO) was
never exercised by a test, while the injected-deps inner functions were fully
covered. The same untested seam also shipped `load_config`-too-strict (fixed by
`load_identity`) and a dropped `hardware_id`.

These tests close that class:

* `test_every_systemd_entrypoint_guards_main` discovers every `ExecStart` from
  the unit files and asserts the target module has a `__main__` guard. Covers the
  missing-guard failure mode for all entrypoints, present and future — including
  `scripts/run-setup-server.py`, which imports `smbus2` at module top and so
  cannot be import-smoke-tested off-Pi (source-level guard check only).
* The behavioral smokes run the real `main()`/`run()` wiring against a realistic
  config with IO mocked at the edges, catching wrong-loader / bad-wiring bugs.

See docs/solutions/integration-issues/systemd-oneshot-python-module-missing-main-entrypoint.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "systemd"


# ---------------------------------------------------------------------------
# The class guard: every systemd entrypoint must actually run when invoked
# ---------------------------------------------------------------------------

def _discover_entrypoint_files() -> list[tuple[str, Path]]:
    """Parse ExecStart= from every unit file and map to its source file.

    Returns (label, path) pairs for `python -m sunset_cam.X` modules and for
    `scripts/Y.py` script entrypoints. Discovery is from the unit files so a new
    service automatically gets guard-checked — the test can't silently drift.
    """
    found: dict[str, Path] = {}
    for unit in sorted(SYSTEMD_DIR.glob("*.service")):
        for line in unit.read_text().splitlines():
            line = line.strip()
            if not line.startswith("ExecStart="):
                continue
            m = re.search(r"-m\s+(sunset_cam\.[\w.]+)", line)
            if m:
                dotted = m.group(1)
                rel = "src/" + dotted.replace(".", "/") + ".py"
                found[dotted] = REPO_ROOT / rel
                continue
            m = re.search(r"(scripts/[\w./-]+\.py)", line)
            if m:
                found[m.group(1)] = REPO_ROOT / m.group(1)
    return sorted(found.items())


def test_every_systemd_entrypoint_guards_main():
    entrypoints = _discover_entrypoint_files()
    # Guard against vacuous pass: discovery must actually find the units.
    assert entrypoints, "discovered no ExecStart entrypoints in systemd/*.service"

    missing = []
    for label, path in entrypoints:
        assert path.exists(), f"{label}: entrypoint file {path} does not exist"
        src = path.read_text()
        has_guard = 'if __name__ == "__main__"' in src or "if __name__ == '__main__'" in src
        if not (has_guard and "main()" in src):
            missing.append(label)
    assert not missing, (
        "these systemd entrypoints lack an `if __name__ == \"__main__\": main()` "
        f"guard and will run-but-do-nothing under `python -m`/script exec: {missing}"
    )


# ---------------------------------------------------------------------------
# supervisor: comes ONLINE on an identity-only config (the sibling-bug seam)
# ---------------------------------------------------------------------------

def test_supervisor_main_comes_online_on_identity_only_config(tmp_path, monkeypatch):
    """The supervisor must register + heartbeat for a freshly-provisioned device
    that has identity ONLY (no capture config). Uses a real identity-only config
    file, so a regression from `load_identity` back to the strict `load_config`
    raises ConfigError here and fails this test."""
    from sunset_cam import supervisor

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "claim_code": "SUNSET-AAAA-BBBB",
        "camera_id": 2,
        "device_token": "tok-xyz",
        "api_base": "https://sunrisesunset.studio",
        "hardware_id": "hw-sunset-cam-2",
    }))
    monkeypatch.setattr(supervisor, "CONFIG_PATH", str(cfg))

    calls = {"register": 0, "heartbeat": 0}

    monkeypatch.setattr(
        supervisor, "register_on_start",
        lambda config, **k: calls.__setitem__("register", calls["register"] + 1) or {},
    )
    monkeypatch.setattr(
        supervisor, "post_heartbeat",
        lambda config, **k: (calls.__setitem__("heartbeat", calls["heartbeat"] + 1)
                             or {"placement_status": "idle", "directives": []}),
    )

    class _FakeController:
        def set_mode(self, mode):  # no shelling out to systemctl in a test
            pass

    monkeypatch.setattr(supervisor, "SystemctlController", lambda: _FakeController())

    class _StopLoop(BaseException):
        """Not an Exception — the loop body's `except Exception` won't swallow it."""

    def _stop(_seconds):
        raise _StopLoop

    monkeypatch.setattr(supervisor.time, "sleep", _stop)

    with pytest.raises(_StopLoop):
        supervisor.main(interval_s=0)

    assert calls["register"] == 1, "supervisor did not register on start"
    assert calls["heartbeat"] >= 1, "supervisor did not heartbeat"


# ---------------------------------------------------------------------------
# capture entrypoint (sunset_cam.main): argv guard + one in-window upload
# ---------------------------------------------------------------------------

def _full_capture_config(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "camera_id": 2,
        "device_token": "tok-xyz",
        "api_base": "https://sunrisesunset.studio",
        "phase": "sunset",
        "window_id": "2026-05-03-sunset-cam2",
        "capture_window_start_utc": "2026-05-03T01:00:00Z",
        "capture_window_end_utc": "2026-05-03T02:30:00Z",
        "capture_interval_s": 1.0,
    }))
    return p


def test_capture_main_rejects_bad_argv(monkeypatch):
    from sunset_cam import main as capture_main

    monkeypatch.setattr(sys, "argv", ["prog"])  # missing the config path arg
    with pytest.raises(SystemExit) as exc:
        capture_main.main()
    assert exc.value.code == 2


def test_capture_main_uploads_one_frame_when_in_window(tmp_path, monkeypatch):
    from sunset_cam import main as capture_main
    from sunset_cam import capture as capture_mod

    cfg = _full_capture_config(tmp_path)

    # Reset the module-level run flag (a prior test may have flipped it).
    monkeypatch.setattr(capture_main, "_running", True)
    # Inside the capture window for this one iteration.
    monkeypatch.setattr(capture_main, "is_active_now", lambda config, now: True)
    # capture_jpeg is imported inside the loop -> patch on the capture module.
    monkeypatch.setattr(capture_mod, "capture_jpeg", lambda: b"\xff\xd8jpeg")
    monkeypatch.setattr(capture_mod, "shutdown", lambda: None, raising=False)

    uploads = []
    monkeypatch.setattr(
        capture_main, "upload_snapshot",
        lambda config, jpeg, now: uploads.append(jpeg) or {"snapshot_id": "s1"},
    )

    # Break the loop after the first iteration's sleep.
    def _stop(_seconds):
        capture_main._running = False

    monkeypatch.setattr(capture_main.time, "sleep", _stop)

    rc = capture_main.run(str(cfg))

    assert rc == 0
    assert uploads == [b"\xff\xd8jpeg"], "capture entrypoint did not upload one frame"


# ---------------------------------------------------------------------------
# SETUP-time script entrypoints (scripts/*.py): main() wires up and serves
# ---------------------------------------------------------------------------

def _load_script(filename: str):
    """Import a scripts/*.py file as a module (scripts/ isn't a package)."""
    import importlib.util

    path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename[:-3].replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_setup_app_main_serves_the_portal(monkeypatch):
    mod = _load_script("run-setup-app.py")

    served = {}

    class _FakeApp:
        def run(self, **kw):
            served.update(kw)

    monkeypatch.setattr(mod, "WifiSetupService", lambda *a, **k: object())
    monkeypatch.setattr(mod, "scan_networks", lambda *a, **k: [])
    monkeypatch.setattr(mod, "create_app", lambda **kw: _FakeApp())

    mod.main()

    assert served.get("port") == 80, "captive-portal entrypoint did not serve on port 80"


def test_run_setup_server_main_imports_off_pi_and_serves(monkeypatch):
    # Imports cleanly only because `smbus2` is now lazy (would ImportError otherwise).
    mod = _load_script("run-setup-server.py")

    monkeypatch.setattr(
        sys, "argv",
        ["prog", "--lat", "48.75", "--lng", "-122.48", "--phase", "sunset"],
    )
    served = {}
    monkeypatch.setattr(mod, "AimingService", lambda **kw: object())
    monkeypatch.setattr(mod, "serve", lambda service, port: served.update(port=port))
    monkeypatch.setattr(mod, "make_orientation_reader", lambda bus: None, raising=False)
    monkeypatch.setattr(mod, "post_placement", lambda *a, **k: None, raising=False)

    mod.main()

    assert served.get("port") == 8080, "aiming setup-server entrypoint did not reach serve()"
