"""Tests for WifiSetupService — connect via nmcli (saves profile + joins in one call)."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# connect — happy path
# ---------------------------------------------------------------------------

def test_connect_calls_runner():
    """connect() must invoke the injected runner exactly once."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("TestNet", "s3cr3t")
    assert len(calls) == 1


def test_connect_runner_receives_list():
    """The runner must receive a list (suitable for subprocess.run)."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("TestNet", "s3cr3t")
    assert isinstance(calls[0], list)


def test_connect_calls_nmcli_device_wifi_connect():
    """Runner args must use nmcli device wifi connect."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("HomeNet", "pass123")
    args = calls[0]
    assert args[:4] == ["nmcli", "device", "wifi", "connect"]


def test_connect_passes_ssid_as_positional_arg():
    """SSID must appear as an argument after 'connect'."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("HomeNet", "pass123")
    args = calls[0]
    assert "HomeNet" in args


def test_connect_passes_psk_after_password_keyword():
    """PSK must appear after the 'password' keyword in the arg list."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("HomeNet", "pass123")
    args = calls[0]
    assert "password" in args
    pw_idx = args.index("password")
    assert args[pw_idx + 1] == "pass123"


def test_connect_full_arg_list():
    """Full expected nmcli command: nmcli device wifi connect <ssid> password <psk>."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("MySSID", "MyPass")
    assert calls[0] == ["nmcli", "device", "wifi", "connect", "MySSID", "password", "MyPass"]


# ---------------------------------------------------------------------------
# connect — empty / whitespace SSID → ValueError, runner never called
# ---------------------------------------------------------------------------

def test_connect_empty_ssid_raises_value_error():
    from sunset_cam.wifi_setup import WifiSetupService
    svc = WifiSetupService(runner=lambda args: None)
    with pytest.raises(ValueError):
        svc.connect("", "password")


def test_connect_whitespace_ssid_raises_value_error():
    from sunset_cam.wifi_setup import WifiSetupService
    svc = WifiSetupService(runner=lambda args: None)
    with pytest.raises(ValueError):
        svc.connect("   ", "password")


def test_connect_empty_ssid_runner_not_called():
    """When SSID is invalid, runner must never be invoked."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    try:
        svc.connect("", "pw")
    except ValueError:
        pass
    assert calls == []


# ---------------------------------------------------------------------------
# connect — ssid/psk passed through as-is (nmcli handles quoting)
# ---------------------------------------------------------------------------

def test_connect_ssid_with_spaces_passed_as_is():
    """Spaces in SSID/PSK are passed as-is — nmcli receives them via argv."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect("My Home Network", "my pass phrase")
    args = calls[0]
    assert "My Home Network" in args
    assert "my pass phrase" in args


def test_connect_ssid_with_special_chars_not_shell_escaped():
    """No shell escaping in argv — characters are passed verbatim."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=calls.append)
    svc.connect('Net"Work', 'pa"ss')
    args = calls[0]
    assert 'Net"Work' in args
    assert 'pa"ss' in args


# ---------------------------------------------------------------------------
# No subprocess fires in tests (runner is always injected)
# ---------------------------------------------------------------------------

def test_no_subprocess_called_by_default_in_tests():
    """Injected runner means no real subprocess ever fires in the test suite."""
    from sunset_cam.wifi_setup import WifiSetupService
    noop = lambda args: None  # noqa: E731
    svc = WifiSetupService(runner=noop)
    svc.connect("SomeNet", "somepass")  # must not raise
