"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List

WPA_PATH = "/etc/wpa_supplicant/wpa_supplicant.conf"


def has_wifi_credentials(wpa_path: str) -> bool:
    """True when a wpa_supplicant file with a network={ block exists."""
    p = Path(wpa_path)
    if not p.exists():
        return False
    try:
        return "network={" in p.read_text()
    except OSError:
        return False


def decide_boot_state(wifi_check: Callable[[], bool]) -> str:
    """'online' when WiFi creds exist, else 'setup' (run the captive portal)."""
    return "online" if wifi_check() else "setup"


def wipe_wifi_credentials(wpa_path: str) -> None:
    """Remove the wpa_supplicant credentials file so the device re-enters SETUP
    on next boot. Idempotent: silently succeeds when the file is already absent."""
    p = Path(wpa_path)
    try:
        p.unlink()
    except FileNotFoundError:
        pass


def dispatch_boot(*, wifi_check: Callable[[], bool], runner: Callable[[List[str]], None]) -> str:
    """Decide SETUP vs ONLINE and start the matching systemd target. Returns the state.

    SETUP  -> start the captive-portal stack (sunset-cam-setup.service).
    ONLINE -> start the supervisor (sunset-cam-supervisor.service); wpa_supplicant
              joins home WiFi on its own from the creds file.

    Both ``wifi_check`` and ``runner`` are injected for testability; the real
    ``main()`` wires in ``has_wifi_credentials(WPA_PATH)`` and ``subprocess.run``.
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
        wifi_check=lambda: has_wifi_credentials(WPA_PATH),
        runner=lambda args: subprocess.run(args, check=True),
    )
