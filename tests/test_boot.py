"""Tests for boot-time SETUP vs ONLINE decision logic (nmcli-based)."""
from __future__ import annotations


# ---------------------------------------------------------------------------
# has_wifi_credentials — nmcli injected runner
# ---------------------------------------------------------------------------

def _nmcli_out(*lines: str) -> str:
    """Build a fake nmcli -t output string from the given lines."""
    return "\n".join(lines) + "\n"


def test_has_wifi_credentials_true_when_wireless_connection_present():
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out("HomeWifi:802-11-wireless")
    assert has_wifi_credentials(runner=lambda _: out) is True


def test_has_wifi_credentials_true_with_multiple_types():
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out(
        "Wired connection 1:802-3-ethernet",
        "HomeWifi:802-11-wireless",
    )
    assert has_wifi_credentials(runner=lambda _: out) is True


def test_has_wifi_credentials_false_when_only_ethernet():
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out("Wired connection 1:802-3-ethernet")
    assert has_wifi_credentials(runner=lambda _: out) is False


def test_has_wifi_credentials_false_when_empty_output():
    from sunset_cam.boot import has_wifi_credentials
    assert has_wifi_credentials(runner=lambda _: "") is False


def test_has_wifi_credentials_false_when_only_loopback():
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out("lo:loopback")
    assert has_wifi_credentials(runner=lambda _: out) is False


def test_has_wifi_credentials_runner_receives_nmcli_list_command():
    """Runner must be called with the expected nmcli command."""
    from sunset_cam.boot import has_wifi_credentials
    captured = []

    def capturing_runner(args):
        captured.append(args)
        return ""

    has_wifi_credentials(runner=capturing_runner)
    assert len(captured) == 1
    assert captured[0] == ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"]


# ---------------------------------------------------------------------------
# wipe_wifi_credentials — nmcli injected runner
# ---------------------------------------------------------------------------

def test_wipe_wifi_credentials_deletes_wifi_connections():
    from sunset_cam.boot import wipe_wifi_credentials
    out = _nmcli_out(
        "HomeWifi:802-11-wireless",
        "Wired connection 1:802-3-ethernet",
        "WorkWifi:802-11-wireless",
    )
    calls = []

    def runner(args):
        calls.append(args)
        return out  # list call returns the output; delete calls return empty

    wipe_wifi_credentials(runner=runner)

    # First call is the list; subsequent calls are deletes
    delete_calls = [c for c in calls if "delete" in c]
    assert len(delete_calls) == 2
    # Both wifi connection names must appear in delete calls
    deleted_names = {c[c.index("delete") + 1] for c in delete_calls}
    assert "HomeWifi" in deleted_names
    assert "WorkWifi" in deleted_names


def test_wipe_wifi_credentials_does_not_delete_ethernet():
    from sunset_cam.boot import wipe_wifi_credentials
    out = _nmcli_out(
        "HomeWifi:802-11-wireless",
        "Wired connection 1:802-3-ethernet",
    )
    calls = []

    def runner(args):
        calls.append(args)
        return out

    wipe_wifi_credentials(runner=runner)
    delete_calls = [c for c in calls if "delete" in c]
    deleted_names = {c[c.index("delete") + 1] for c in delete_calls}
    assert "Wired connection 1" not in deleted_names


def test_wipe_wifi_credentials_noop_when_no_wifi_connections():
    from sunset_cam.boot import wipe_wifi_credentials
    out = _nmcli_out("Wired connection 1:802-3-ethernet")
    calls = []

    def runner(args):
        calls.append(args)
        return out

    wipe_wifi_credentials(runner=runner)
    delete_calls = [c for c in calls if "delete" in c]
    assert delete_calls == []


def test_wipe_wifi_credentials_unescapes_colons_in_name():
    """nmcli escapes colons in SSIDs as \\: — we must unescape before delete."""
    from sunset_cam.boot import wipe_wifi_credentials
    # An SSID that literally contains a colon: "My:Net"
    out = _nmcli_out("My\\:Net:802-11-wireless")
    calls = []

    def runner(args):
        calls.append(args)
        return out

    wipe_wifi_credentials(runner=runner)
    delete_calls = [c for c in calls if "delete" in c]
    assert len(delete_calls) == 1
    assert delete_calls[0][delete_calls[0].index("delete") + 1] == "My:Net"


# ---------------------------------------------------------------------------
# decide_boot_state — stays injectable, unchanged logic
# ---------------------------------------------------------------------------

def test_decide_setup_when_no_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: False) == "setup"


def test_decide_online_when_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: True) == "online"


# ---------------------------------------------------------------------------
# dispatch_boot — stays injectable, unchanged logic
# ---------------------------------------------------------------------------

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
