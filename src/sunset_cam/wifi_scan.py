"""Scan for nearby WiFi networks via NetworkManager (``nmcli``).

The ship OS (current Raspberry Pi OS) manages WiFi with NetworkManager, so we
scan with ``nmcli ... device wifi list`` rather than the old ``iwlist``.
"""
from __future__ import annotations

import subprocess
from typing import Callable


def _default_nmcli_runner(args: list) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def scan_networks(runner: Callable[[list], str] = _default_nmcli_runner) -> list[dict]:
    """Return nearby WiFi networks (parsed, sorted, de-duped). Never raises — a
    failed scan yields ``[]`` so the captive portal still renders."""
    try:
        out = runner(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
        )
    except Exception:  # noqa: BLE001 — a scan failure must not break the portal
        return []
    return parse_nmcli_wifi(out)


def parse_nmcli_wifi(output: str) -> list[dict]:
    """Parse terse ``nmcli -t -f SSID,SIGNAL,SECURITY device wifi list`` output.

    Each line is ``SSID:SIGNAL:SECURITY`` (e.g. ``Home Net:58:WPA1 WPA2``).
    Returns ``{"ssid": str, "signal": int, "encrypted": bool}`` dicts sorted by
    signal (0-100) descending; blank/hidden SSIDs dropped; duplicates de-duped
    keeping the strongest.
    """
    best: dict[str, dict] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        # SSID may contain escaped colons (\:); SIGNAL and SECURITY never do, so
        # split the two rightmost colons off and treat the rest as the SSID.
        parts = line.rsplit(":", 2)
        if len(parts) != 3:
            continue
        raw_ssid, raw_signal, raw_security = parts
        ssid = raw_ssid.replace("\\:", ":").replace("\x00", "").strip()
        if not ssid:
            continue  # hidden / blank
        try:
            signal = int(raw_signal)
        except ValueError:
            signal = 0
        security = raw_security.strip()
        encrypted = bool(security) and security != "--"
        network = {"ssid": ssid, "signal": signal, "encrypted": encrypted}
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = network
    return sorted(best.values(), key=lambda n: n["signal"], reverse=True)
