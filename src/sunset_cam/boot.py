"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations

import subprocess
from typing import Callable, List


def _default_nmcli_runner(args: list) -> str:
    """Run a command and return its stdout. Never raises on non-zero exit."""
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def has_wifi_credentials(runner: Callable[[list], str] = _default_nmcli_runner) -> bool:
    """True when NetworkManager has at least one saved WiFi (802-11-wireless) connection."""
    out = runner(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    for line in out.splitlines():
        # -t output is colon-separated; TYPE is the last field. NAMEs may contain
        # escaped colons (\:) but the TYPE token is stable at the end.
        if line.strip().endswith("802-11-wireless"):
            return True
    return False


def decide_boot_state(wifi_check: Callable[[], bool]) -> str:
    """'online' when WiFi creds exist, else 'setup' (run the captive portal)."""
    return "online" if wifi_check() else "setup"


def wipe_wifi_credentials(runner: Callable[[list], str] = _default_nmcli_runner) -> None:
    """Delete all saved WiFi connections so the device re-enters SETUP next boot."""
    out = runner(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    for line in out.splitlines():
        if line.strip().endswith("802-11-wireless"):
            name = line.rsplit(":", 1)[0]
            # un-escape nmcli's \: in NAME
            name = name.replace("\\:", ":")
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
