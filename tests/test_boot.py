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


def test_has_wifi_credentials_false_when_only_setup_ap():
    """sunset-setup-ap is our own AP profile — not a home credential → False."""
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out("sunset-setup-ap:802-11-wireless")
    assert has_wifi_credentials(runner=lambda _: out) is False


def test_has_wifi_credentials_true_when_setup_ap_and_real_wifi():
    """If a real home WiFi is also present alongside the AP profile → True."""
    from sunset_cam.boot import has_wifi_credentials
    out = _nmcli_out(
        "sunset-setup-ap:802-11-wireless",
        "HomeWifi:802-11-wireless",
    )
    assert has_wifi_credentials(runner=lambda _: out) is True


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


def test_wipe_wifi_credentials_does_not_delete_setup_ap():
    """wipe must skip the sunset-setup-ap profile — it is not a home credential."""
    from sunset_cam.boot import wipe_wifi_credentials
    out = _nmcli_out(
        "sunset-setup-ap:802-11-wireless",
        "HomeWifi:802-11-wireless",
    )
    calls = []

    def runner(args):
        calls.append(args)
        return out

    wipe_wifi_credentials(runner=runner)
    delete_calls = [c for c in calls if "delete" in c]
    deleted_names = {c[c.index("delete") + 1] for c in delete_calls}
    assert "sunset-setup-ap" not in deleted_names
    assert "HomeWifi" in deleted_names


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
        online_check=lambda: False,
        runner=lambda args: calls.append(args),
        sleep=lambda _: None,
    )
    assert state == "setup"
    assert ["systemctl", "start", "sunset-cam-setup.service"] in calls


def test_dispatch_boot_creds_present_starts_supervisor():
    """Creds present + immediately online → state='online' AND runner called with sunset-cam-supervisor.service."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    state = dispatch_boot(
        wifi_check=lambda: True,
        online_check=lambda: True,
        runner=lambda args: calls.append(args),
        sleep=lambda _: None,
    )
    assert state == "online"
    assert ["systemctl", "start", "sunset-cam-supervisor.service"] in calls


def test_dispatch_boot_setup_does_not_start_supervisor():
    """In SETUP mode, the supervisor service must NOT be started."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    dispatch_boot(
        wifi_check=lambda: False,
        online_check=lambda: False,
        runner=lambda args: calls.append(args),
        sleep=lambda _: None,
    )
    started = [a for a in calls if "start" in a]
    assert not any("sunset-cam-supervisor.service" in a for a in started)


def test_dispatch_boot_online_does_not_start_setup():
    """In ONLINE mode, the setup service must NOT be started."""
    from sunset_cam.boot import dispatch_boot
    calls = []
    dispatch_boot(
        wifi_check=lambda: True,
        online_check=lambda: True,
        runner=lambda args: calls.append(args),
        sleep=lambda _: None,
    )
    started = [a for a in calls if "start" in a]
    assert not any("sunset-cam-setup.service" in a for a in started)


# ---------------------------------------------------------------------------
# is_online — active connection check
# ---------------------------------------------------------------------------

def _active_nmcli_out(*lines: str) -> str:
    """Build a fake 'nmcli -t -f NAME,TYPE connection show --active' output."""
    return "\n".join(lines) + "\n"


def test_is_online_true_when_active_home_wifi():
    """Active home WiFi connection → True."""
    from sunset_cam.boot import is_online
    out = _active_nmcli_out("HomeWifi:802-11-wireless")
    assert is_online(runner=lambda _: out) is True


def test_is_online_false_when_only_setup_ap_active():
    """Only our own setup AP is active → False (not a real join)."""
    from sunset_cam.boot import is_online
    out = _active_nmcli_out("sunset-setup-ap:802-11-wireless")
    assert is_online(runner=lambda _: out) is False


def test_is_online_false_when_only_ethernet_active():
    """Only ethernet active, no WiFi → False."""
    from sunset_cam.boot import is_online
    out = _active_nmcli_out("Wired connection 1:802-3-ethernet")
    assert is_online(runner=lambda _: out) is False


def test_is_online_false_when_empty_output():
    """No active connections → False."""
    from sunset_cam.boot import is_online
    assert is_online(runner=lambda _: "") is False


def test_is_online_true_with_colon_in_ssid():
    """SSID containing an escaped colon (\\:) is not the setup AP → True."""
    from sunset_cam.boot import is_online
    # "My:Net" as nmcli would escape it
    out = _active_nmcli_out("My\\:Net:802-11-wireless")
    assert is_online(runner=lambda _: out) is True


# ---------------------------------------------------------------------------
# dispatch_boot (new signature) — wait-for-join + fallback
# ---------------------------------------------------------------------------

def _make_recording_runner():
    calls = []
    return calls, lambda args: calls.append(args)


def _make_sleep_counter():
    count = [0]

    def counting_sleep(seconds):
        count[0] += 1

    return count, counting_sleep


def test_dispatch_boot_no_creds_starts_setup_never_sleeps():
    """No creds → 'setup', starts setup service, zero sleeps."""
    from sunset_cam.boot import dispatch_boot
    calls, runner = _make_recording_runner()
    sleep_count, counting_sleep = _make_sleep_counter()

    state = dispatch_boot(
        wifi_check=lambda: False,
        online_check=lambda: False,
        runner=runner,
        sleep=counting_sleep,
    )

    assert state == "setup"
    assert ["systemctl", "start", "sunset-cam-setup.service"] in calls
    assert sleep_count[0] == 0


def test_dispatch_boot_creds_online_immediately_starts_supervisor_no_sleep():
    """Creds + online immediately → 'online', starts supervisor, zero sleeps."""
    from sunset_cam.boot import dispatch_boot
    calls, runner = _make_recording_runner()
    sleep_count, counting_sleep = _make_sleep_counter()

    state = dispatch_boot(
        wifi_check=lambda: True,
        online_check=lambda: True,
        runner=runner,
        sleep=counting_sleep,
    )

    assert state == "online"
    assert ["systemctl", "start", "sunset-cam-supervisor.service"] in calls
    assert sleep_count[0] == 0


def test_dispatch_boot_creds_online_on_third_poll():
    """Creds + online_check True on 3rd call → 'online', 2 sleeps."""
    from sunset_cam.boot import dispatch_boot
    calls, runner = _make_recording_runner()
    sleep_count, counting_sleep = _make_sleep_counter()

    poll_count = [0]

    def online_check_on_third():
        poll_count[0] += 1
        return poll_count[0] >= 3

    state = dispatch_boot(
        wifi_check=lambda: True,
        online_check=online_check_on_third,
        runner=runner,
        sleep=counting_sleep,
        retries=5,
        interval=0,
    )

    assert state == "online"
    assert ["systemctl", "start", "sunset-cam-supervisor.service"] in calls
    assert sleep_count[0] == 2  # slept after poll 1 and poll 2


def test_dispatch_boot_creds_timeout_falls_back_to_setup():
    """Creds + online_check always False → 'setup-fallback', starts setup, slept `retries` times."""
    from sunset_cam.boot import dispatch_boot
    calls, runner = _make_recording_runner()
    sleep_count, counting_sleep = _make_sleep_counter()

    retries = 4
    state = dispatch_boot(
        wifi_check=lambda: True,
        online_check=lambda: False,
        runner=runner,
        sleep=counting_sleep,
        retries=retries,
        interval=0,
    )

    assert state == "setup-fallback"
    assert ["systemctl", "start", "sunset-cam-setup.service"] in calls
    assert sleep_count[0] == retries
