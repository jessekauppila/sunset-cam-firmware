"""Parse ``iwlist wlan0 scan`` output into a structured list of networks."""
from __future__ import annotations

import re


def parse_iwlist(output: str) -> list[dict]:
    """Parse ``iwlist wlan0 scan`` text.

    Returns a list of ``{"ssid": str, "signal_dbm": int | None, "encrypted": bool}``
    sorted by signal strength descending (networks with no signal sort last).
    Blank / hidden SSIDs (empty or containing only null bytes) are dropped.
    Duplicate SSIDs are de-duplicated, keeping the entry with the strongest signal.
    """
    if not output.strip():
        return []

    # Split into per-cell blocks on the "Cell XX - " marker
    blocks = re.split(r"\n?\s*Cell \d+ - ", output)

    # First element is the header line ("wlan0  Scan completed :"), skip it.
    cells = blocks[1:]

    best: dict[str, dict] = {}  # ssid -> network dict (strongest so far)

    for cell in cells:
        ssid = _parse_essid(cell)
        if not ssid:
            continue  # drop blank / hidden / null-byte SSIDs

        signal_dbm = _parse_signal(cell)
        encrypted = _parse_encrypted(cell)

        network = {"ssid": ssid, "signal_dbm": signal_dbm, "encrypted": encrypted}

        if ssid not in best:
            best[ssid] = network
        else:
            # Keep the one with the stronger (less-negative) signal.
            existing = best[ssid]["signal_dbm"]
            if signal_dbm is not None and (existing is None or signal_dbm > existing):
                best[ssid] = network

    # Sort by signal descending; None sorts last.
    return sorted(
        best.values(),
        key=lambda n: n["signal_dbm"] if n["signal_dbm"] is not None else float("-inf"),
        reverse=True,
    )


_ESSID_RE = re.compile(r'ESSID:"(.*?)"', re.DOTALL)
_SIGNAL_RE = re.compile(r"Signal level=(-?\d+)\s*dBm", re.IGNORECASE)
_ENC_KEY_RE = re.compile(r"Encryption key:(on|off)", re.IGNORECASE)


def _parse_essid(cell: str) -> str:
    """Return the SSID string, or '' if absent / hidden / blank / null-byte-only."""
    m = _ESSID_RE.search(cell)
    if not m:
        return ""
    raw = m.group(1)
    # Drop entirely if the value is empty or consists only of null bytes / whitespace
    stripped = raw.replace("\x00", "").strip()
    return stripped  # empty string if hidden


def _parse_signal(cell: str) -> int | None:
    """Return signal level in dBm, or None when the line is absent."""
    m = _SIGNAL_RE.search(cell)
    return int(m.group(1)) if m else None


def _parse_encrypted(cell: str) -> bool:
    """Return True when 'Encryption key:on', False otherwise."""
    m = _ENC_KEY_RE.search(cell)
    if m:
        return m.group(1).lower() == "on"
    return False
