"""Save a WiFi profile via NetworkManager (nmcli) without activating it.

On a single-radio Pi running as a captive-portal AP, calling
``nmcli device wifi connect`` inside an HTTP handler races the AP radio
and causes a Flask 500.  Instead we:
  1. Delete any existing profile with the same con-name (idempotent).
  2. Add a new profile with ``autoconnect yes`` (no activation).
  3. Return so the portal can send its response.
  4. The caller (setup_app) then schedules a reboot; NetworkManager joins
     the saved network automatically on the next boot.

The runner is injected so the class is fully testable without any real
hardware or nmcli binary present.
"""
from __future__ import annotations

import subprocess
from typing import Callable


def _default_runner(args: list) -> None:
    subprocess.run(args, check=True, timeout=30)


class WifiSetupService:
    """Save a WiFi profile via nmcli (no immediate activation).

    Parameters
    ----------
    runner:
        Callable that receives a list of args and executes them (defaults to
        ``subprocess.run``). Inject a mock in tests to avoid real nmcli calls.
    """

    def __init__(
        self,
        runner: Callable[[list], None] = _default_runner,
    ) -> None:
        self._runner = runner

    def connect(self, ssid: str, psk: str) -> None:
        """Save a NetworkManager WiFi profile for *ssid*.

        Deletes any existing profile with the same SSID con-name first so
        re-onboarding is idempotent.  The deletion is best-effort: if the
        profile does not exist yet, the error is silently ignored.

        Does NOT activate the connection — the radio stays in AP mode so the
        portal can flush its HTTP response.  The caller should schedule a
        reboot; NetworkManager will join the saved network on the next boot.

        Raises
        ------
        ValueError
            When *ssid* is empty or whitespace-only.
        """
        if not ssid or not ssid.strip():
            raise ValueError(f"SSID must not be empty, got: {ssid!r}")

        # Delete any pre-existing profile for this SSID (ignore failures).
        try:
            self._runner(["nmcli", "connection", "delete", ssid])
        except Exception:
            pass  # no existing profile is fine

        # Build the add command: type wifi, con-name = ssid, autoconnect yes.
        args = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", ssid,
            "ssid", ssid,
            "autoconnect", "yes",
        ]
        if psk:
            args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk]

        self._runner(args)
