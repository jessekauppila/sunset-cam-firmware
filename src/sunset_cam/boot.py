"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations

import subprocess
import time
from typing import Callable, List

# The AP profile created by scripts/setup-ap.sh — not a home WiFi credential.
SETUP_AP_CON = "sunset-setup-ap"

# Timeout parameters for waiting on NetworkManager to associate + DHCP.
ONLINE_WAIT_RETRIES = 12       # 12 * 5s = ~60s for NM to associate + DHCP
ONLINE_WAIT_INTERVAL_S = 5


def _default_nmcli_runner(args: list) -> str:
    """Run a command and return its stdout. Never raises on non-zero exit."""
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def _run(args: list) -> None:
    """Run a command (fire-and-forget, for systemctl). Raises on non-zero exit."""
    subprocess.run(args, check=True)


def has_wifi_credentials(runner: Callable[[list], str] = _default_nmcli_runner) -> bool:
    """True when NetworkManager has at least one saved home WiFi connection.

    Excludes the setup AP profile (``sunset-setup-ap``) — that is our own AP,
    not a home credential.  A device with only the setup AP profile still needs
    to run the captive portal.
    """
    out = runner(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    for line in out.splitlines():
        if not line.strip():
            continue
        # NAME may contain escaped colons (\:); TYPE is the last field.
        name, _, ctype = line.rpartition(":")
        name = name.replace("\\:", ":")
        if ctype.strip() == "802-11-wireless" and name != SETUP_AP_CON:
            return True
    return False


def is_online(runner: Callable[[list], str] = _default_nmcli_runner) -> bool:
    """True when an active 802-11-wireless connection (other than the setup AP)
    exists — i.e. the device has joined a real WiFi network."""
    out = runner(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    for line in out.splitlines():
        if not line.strip():
            continue
        name, _, ctype = line.rpartition(":")
        if ctype.strip() == "802-11-wireless" and name.replace("\\:", ":") != SETUP_AP_CON:
            return True
    return False


def decide_boot_state(wifi_check: Callable[[], bool]) -> str:
    """'online' when WiFi creds exist, else 'setup' (run the captive portal)."""
    return "online" if wifi_check() else "setup"


def wipe_wifi_credentials(runner: Callable[[list], str] = _default_nmcli_runner) -> None:
    """Delete all saved home WiFi connections so the device re-enters SETUP next boot.

    Skips ``sunset-setup-ap`` — that is the captive-portal AP profile, not a
    home credential.
    """
    out = runner(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    for line in out.splitlines():
        if not line.strip():
            continue
        name, _, ctype = line.rpartition(":")
        name = name.replace("\\:", ":")
        if ctype.strip() == "802-11-wireless" and name != SETUP_AP_CON:
            runner(["nmcli", "connection", "delete", name])


def dispatch_boot(
    *,
    wifi_check: Callable[[], bool],
    online_check: Callable[[], bool],
    runner: Callable[[List[str]], None],
    sleep: Callable[[float], None],
    retries: int = ONLINE_WAIT_RETRIES,
    interval: float = ONLINE_WAIT_INTERVAL_S,
) -> str:
    """Decide SETUP vs ONLINE and start the matching systemd target.

    Returns one of:
      'setup'          — no saved creds; starts sunset-cam-setup.service.
      'online'         — creds exist and NM joined the home network; starts
                         sunset-cam-supervisor.service.
      'setup-fallback' — creds exist but NM never joined within the timeout
                         (bad password / network down); falls back to
                         sunset-cam-setup.service so the customer can retry.

    All dependencies (wifi_check, online_check, runner, sleep) are injected for
    testability; real main() wires in has_wifi_credentials, is_online,
    subprocess.run-based runner, and time.sleep.
    """
    state = decide_boot_state(wifi_check)
    if state == "setup":
        runner(["systemctl", "start", "sunset-cam-setup.service"])
        return "setup"

    # online: creds exist — wait for NM to actually join the home network.
    for _ in range(retries):
        if online_check():
            runner(["systemctl", "start", "sunset-cam-supervisor.service"])
            return "online"
        sleep(interval)

    # Join never succeeded (bad password / network down) → re-enter SETUP so the
    # customer can fix it, rather than silently sitting offline forever.
    runner(["systemctl", "start", "sunset-cam-setup.service"])
    return "setup-fallback"


def main() -> None:
    """Boot dispatcher entry point (run as a oneshot by sunset-cam-boot.service).
    No unit test for this thin wiring — all logic is tested via dispatch_boot."""
    dispatch_boot(
        wifi_check=has_wifi_credentials,
        online_check=is_online,
        runner=_run,
        sleep=time.sleep,
    )
