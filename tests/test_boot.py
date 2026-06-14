"""Tests for boot-time SETUP vs ONLINE decision logic."""
from __future__ import annotations


def test_missing_file_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    assert has_wifi_credentials(str(tmp_path / "nope.conf")) is False


def test_file_with_network_block_is_true(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"
    p.write_text('ctrl_interface=...\nnetwork={\n ssid="x"\n psk="y"\n}\n')
    assert has_wifi_credentials(str(p)) is True


def test_file_without_network_block_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"
    p.write_text("ctrl_interface=/run/wpa\n")
    assert has_wifi_credentials(str(p)) is False


def test_decide_setup_when_no_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: False) == "setup"


def test_decide_online_when_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: True) == "online"


def test_wipe_wifi_credentials_removes_existing_file(tmp_path):
    from sunset_cam.boot import wipe_wifi_credentials
    p = tmp_path / "wpa_supplicant.conf"
    p.write_text('network={\n ssid="x"\n psk="y"\n}\n')
    wipe_wifi_credentials(str(p))
    assert not p.exists()


def test_wipe_wifi_credentials_is_idempotent_when_file_absent(tmp_path):
    from sunset_cam.boot import wipe_wifi_credentials
    missing = str(tmp_path / "wpa_supplicant.conf")
    # Must not raise if the file is already gone
    wipe_wifi_credentials(missing)


# --- dispatch_boot tests (TDD for E-1) ---

def test_dispatch_boot_no_creds_starts_setup_service():
    """No creds → state='setup' AND runner called with sunset-cam-setup.service."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    state = dispatch_boot(
        wifi_check=lambda: False,
        runner=lambda args: calls.append(args),
    )
    assert state == "setup"
    assert ["systemctl", "start", "sunset-cam-setup.service"] in calls


def test_dispatch_boot_creds_present_starts_supervisor():
    """Creds present → state='online' AND runner called with sunset-cam-supervisor.service."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    state = dispatch_boot(
        wifi_check=lambda: True,
        runner=lambda args: calls.append(args),
    )
    assert state == "online"
    assert ["systemctl", "start", "sunset-cam-supervisor.service"] in calls


def test_dispatch_boot_setup_does_not_start_supervisor():
    """In SETUP mode, the supervisor service must NOT be started."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    dispatch_boot(wifi_check=lambda: False, runner=lambda args: calls.append(args))
    started = [a for a in calls if "start" in a]
    assert not any("sunset-cam-supervisor.service" in a for a in started)


def test_dispatch_boot_online_does_not_start_setup():
    """In ONLINE mode, the setup service must NOT be started."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    dispatch_boot(wifi_check=lambda: True, runner=lambda args: calls.append(args))
    started = [a for a in calls if "start" in a]
    assert not any("sunset-cam-setup.service" in a for a in started)
