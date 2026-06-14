"""Tests for WifiSetupService — write wpa_supplicant creds + trigger join."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# write_credentials
# ---------------------------------------------------------------------------


def test_write_credentials_creates_file(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    svc = WifiSetupService(wpa_path=wpa)
    svc.write_credentials("TestNet", "s3cr3t")
    from pathlib import Path
    assert Path(wpa).exists()


def test_write_credentials_contains_network_block(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("TestNet", "s3cr3t")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert "network={" in text


def test_write_credentials_has_wifi_credentials_returns_true(tmp_path):
    """The written file must satisfy has_wifi_credentials in boot.py."""
    from sunset_cam.wifi_setup import WifiSetupService
    from sunset_cam.boot import has_wifi_credentials
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("TestNet", "s3cr3t")
    assert has_wifi_credentials(wpa) is True


def test_write_credentials_includes_ssid(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("MyHome", "pass123")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert 'ssid="MyHome"' in text


def test_write_credentials_includes_psk(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("MyHome", "pass123")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert 'psk="pass123"' in text


def test_write_credentials_includes_ctrl_interface(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("MyHome", "pass123")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert "ctrl_interface=" in text


def test_write_credentials_includes_country(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("MyHome", "pass123")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert "country=US" in text


def test_write_credentials_empty_ssid_raises(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    svc = WifiSetupService(wpa_path=wpa)
    with pytest.raises(ValueError):
        svc.write_credentials("", "password")


def test_write_credentials_whitespace_ssid_raises(tmp_path):
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    svc = WifiSetupService(wpa_path=wpa)
    with pytest.raises(ValueError):
        svc.write_credentials("   ", "password")


def test_write_credentials_ssid_with_quote_escaped(tmp_path):
    """Double-quotes in the SSID must be escaped so the conf stays valid."""
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials('Net"Work', "pass")
    from pathlib import Path
    text = Path(wpa).read_text()
    # The embedded quote should be escaped
    assert '\\"' in text


def test_write_credentials_psk_with_quote_escaped(tmp_path):
    """Double-quotes in the PSK must be escaped."""
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    WifiSetupService(wpa_path=wpa).write_credentials("MyNet", 'pa"ss')
    from pathlib import Path
    text = Path(wpa).read_text()
    assert '\\"' in text


def test_write_credentials_overwrites_existing(tmp_path):
    """Calling twice replaces the old creds completely."""
    from sunset_cam.wifi_setup import WifiSetupService
    wpa = str(tmp_path / "wpa_supplicant.conf")
    svc = WifiSetupService(wpa_path=wpa)
    svc.write_credentials("OldNet", "oldpass")
    svc.write_credentials("NewNet", "newpass")
    from pathlib import Path
    text = Path(wpa).read_text()
    assert "NewNet" in text
    assert "OldNet" not in text


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------


def test_join_calls_runner(tmp_path):
    """join() must invoke the injected runner."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(wpa_path=str(tmp_path / "wpa.conf"), runner=calls.append)
    svc.join()
    assert len(calls) == 1


def test_join_runner_receives_list(tmp_path):
    """The runner must receive a list (args for subprocess.run)."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(wpa_path=str(tmp_path / "wpa.conf"), runner=calls.append)
    svc.join()
    assert isinstance(calls[0], list)


def test_join_calls_wpa_cli_reconfigure(tmp_path):
    """Runner args should include wpa_cli and reconfigure."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(wpa_path=str(tmp_path / "wpa.conf"), runner=calls.append)
    svc.join()
    args = calls[0]
    assert "wpa_cli" in args
    assert "reconfigure" in args


def test_no_subprocess_called_by_default_in_tests(tmp_path):
    """Injected runner means no real subprocess ever fires in the test suite."""
    from sunset_cam.wifi_setup import WifiSetupService
    # Supplying a no-op runner — if the default (subprocess) were called it
    # would fail because wpa_cli doesn't exist in CI.
    noop = lambda args: None  # noqa: E731
    svc = WifiSetupService(wpa_path=str(tmp_path / "wpa.conf"), runner=noop)
    svc.join()  # must not raise
