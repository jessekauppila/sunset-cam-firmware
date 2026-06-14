"""Tests for WifiSetupService — saves a profile (no activation) then caller reboots."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recording_runner(raise_on_first=False):
    """Return (runner, calls_list).

    If raise_on_first=True the first call raises (simulating 'no existing profile').
    """
    calls = []

    def runner(args):
        calls.append(list(args))
        if raise_on_first and len(calls) == 1:
            raise subprocess.CalledProcessError(10, args)

    return runner, calls


import subprocess


# ---------------------------------------------------------------------------
# connect — deletes existing profile first (idempotent), then adds
# ---------------------------------------------------------------------------

def test_connect_deletes_before_adding():
    """connect() must attempt to delete an existing profile before adding."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    # First call must be a delete
    assert calls[0][:3] == ["nmcli", "connection", "delete"]


def test_connect_delete_uses_ssid_as_con_name():
    """The delete call uses the SSID as the connection name."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    delete_call = calls[0]
    assert delete_call == ["nmcli", "connection", "delete", "HomeNet"]


def test_connect_adds_after_delete():
    """connect() must call nmcli connection add after the delete."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_calls = [c for c in calls if "add" in c]
    assert len(add_calls) == 1


def test_connect_add_uses_connection_add():
    """Add call uses: nmcli connection add type wifi ..."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    assert add_call[:4] == ["nmcli", "connection", "add", "type"]
    assert "wifi" in add_call


def test_connect_add_sets_con_name_to_ssid():
    """con-name is set to the SSID value."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    idx = add_call.index("con-name")
    assert add_call[idx + 1] == "HomeNet"


def test_connect_add_sets_ssid():
    """ssid property is set in the add call."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    idx = add_call.index("ssid")
    assert add_call[idx + 1] == "HomeNet"


def test_connect_add_sets_autoconnect_yes():
    """autoconnect yes is set so the Pi joins on next boot."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    idx = add_call.index("autoconnect")
    assert add_call[idx + 1] == "yes"


# ---------------------------------------------------------------------------
# connect — WPA network includes wifi-sec
# ---------------------------------------------------------------------------

def test_connect_wpa_includes_key_mgmt():
    """WPA network: wifi-sec.key-mgmt wpa-psk must appear in the add call."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    assert "wifi-sec.key-mgmt" in add_call
    idx = add_call.index("wifi-sec.key-mgmt")
    assert add_call[idx + 1] == "wpa-psk"


def test_connect_wpa_includes_psk():
    """WPA network: wifi-sec.psk must carry the passphrase."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    add_call = [c for c in calls if "add" in c][0]
    assert "wifi-sec.psk" in add_call
    idx = add_call.index("wifi-sec.psk")
    assert add_call[idx + 1] == "s3cr3t"


# ---------------------------------------------------------------------------
# connect — open network (empty psk) omits wifi-sec entirely
# ---------------------------------------------------------------------------

def test_connect_open_network_omits_wifi_sec_key_mgmt():
    """Open network (empty psk): wifi-sec.key-mgmt must NOT appear."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("OpenNet", "")
    add_call = [c for c in calls if "add" in c][0]
    assert "wifi-sec.key-mgmt" not in add_call


def test_connect_open_network_omits_wifi_sec_psk():
    """Open network (empty psk): wifi-sec.psk must NOT appear."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("OpenNet", "")
    add_call = [c for c in calls if "add" in c][0]
    assert "wifi-sec.psk" not in add_call


# ---------------------------------------------------------------------------
# connect — failing delete (no existing profile) does NOT propagate
# ---------------------------------------------------------------------------

def test_connect_nonfatal_delete_failure_does_not_raise():
    """If delete fails (e.g. no existing profile), connect() must still succeed."""
    from sunset_cam.wifi_setup import WifiSetupService
    call_count = [0]

    def runner(args):
        call_count[0] += 1
        if "delete" in args:
            raise subprocess.CalledProcessError(10, args)
        # add call succeeds silently

    svc = WifiSetupService(runner=runner)
    svc.connect("HomeNet", "pw")  # must not raise
    # add was still called even though delete raised
    assert call_count[0] == 2


def test_connect_add_still_called_after_failed_delete():
    """Even when delete raises, the add call must still be issued."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []

    def runner(args):
        calls.append(list(args))
        if "delete" in args:
            raise subprocess.CalledProcessError(10, args)

    svc = WifiSetupService(runner=runner)
    svc.connect("HomeNet", "pw")
    add_calls = [c for c in calls if "add" in c]
    assert len(add_calls) == 1


# ---------------------------------------------------------------------------
# connect — no activation (no device wifi connect / connection up)
# ---------------------------------------------------------------------------

def test_connect_never_calls_device_wifi_connect():
    """connect() must NOT call nmcli device wifi connect (would disrupt AP)."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    for call in calls:
        # Must not include the activating subcommand sequence
        assert not (len(call) >= 4 and call[:4] == ["nmcli", "device", "wifi", "connect"]), \
            f"Unexpected activation call: {call}"


def test_connect_never_calls_connection_up():
    """connect() must NOT call nmcli connection up (would switch radio)."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("HomeNet", "s3cr3t")
    for call in calls:
        assert not ("connection" in call and "up" in call), \
            f"Unexpected connection up call: {call}"


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
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect("My Home Network", "my pass phrase")
    add_call = [c for c in calls if "add" in c][0]
    assert "My Home Network" in add_call
    assert "my pass phrase" in add_call


def test_connect_ssid_with_special_chars_not_shell_escaped():
    """No shell escaping in argv — characters are passed verbatim."""
    from sunset_cam.wifi_setup import WifiSetupService
    calls = []
    svc = WifiSetupService(runner=lambda a: calls.append(list(a)))
    svc.connect('Net"Work', 'pa"ss')
    add_call = [c for c in calls if "add" in c][0]
    assert 'Net"Work' in add_call
    assert 'pa"ss' in add_call


# ---------------------------------------------------------------------------
# No subprocess fires in tests (runner is always injected)
# ---------------------------------------------------------------------------

def test_no_subprocess_called_by_default_in_tests():
    """Injected runner means no real subprocess ever fires in the test suite."""
    from sunset_cam.wifi_setup import WifiSetupService
    noop = lambda args: None  # noqa: E731
    svc = WifiSetupService(runner=noop)
    svc.connect("SomeNet", "somepass")  # must not raise
