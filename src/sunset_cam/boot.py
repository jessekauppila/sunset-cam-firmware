"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations

from pathlib import Path
from typing import Callable


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
