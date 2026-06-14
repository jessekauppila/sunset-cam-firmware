"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations

import subprocess
from typing import Callable, List

# The AP profile created by scripts/setup-ap.sh — not a home WiFi credential.
SETUP_AP_CON = "sunset-setup-ap"


def _default_nmcli_runner(args: list) -> str:
    """Run a command and return its stdout. Never raises on non-zero exit."""
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


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


def dispatch_boot(*, wifi_check: Callable[[], bool], runner: Callable[[List[str]], None]) -> str:
    """Decide SETUP vs ONLINE and start the matching systemd target. Returns the state.

    SETUP  -> start the captive-portal stack (sunset-cam-setup.service).
    ONLINE -> start the supervisor (sunset-cam-supervisor.service); NetworkManager
              joins home WiFi automatically from its saved connection profile.

    Both ``wifi_check`` and ``runner`` are injected for testability; the real
    ``main()`` wires in ``has_wifi_credentials()`` and ``subprocess.run``.
    """
    state = decide_boot_state(wifi_check)
    if state == "setup":
        runner(["systemctl", "start", "sunset-cam-setup.service"])
    else:
        runner(["systemctl", "start", "sunset-cam-supervisor.service"])
    return state


def main() -> None:
    """Boot dispatcher entry point (run as a oneshot by sunset-cam-boot.service).
    No unit test for this thin wiring — all logic is tested via dispatch_boot."""
    import subprocess

    dispatch_boot(
        wifi_check=has_wifi_credentials,
        runner=lambda args: subprocess.run(args, check=True),
    )
