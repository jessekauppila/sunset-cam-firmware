"""Connect to a WiFi network via NetworkManager (nmcli).

The runner is injected so the class is fully testable without any real
hardware or nmcli binary present. nmcli's ``device wifi connect`` both saves
a connection profile AND joins the network in one call.
"""
from __future__ import annotations

import subprocess
from typing import Callable


def _default_runner(args: list) -> None:
    subprocess.run(args, check=True, timeout=30)


class WifiSetupService:
    """Save a WiFi profile and join the network via nmcli.

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
        """Save a NetworkManager WiFi profile and join the network.

        Uses ``nmcli device wifi connect <ssid> password <psk>`` which both
        creates/updates a connection profile and associates with the AP. nmcli
        receives ssid and psk as separate argv elements — no shell escaping is
        needed in our code.

        Raises
        ------
        ValueError
            When *ssid* is empty or whitespace-only.
        """
        if not ssid or not ssid.strip():
            raise ValueError(f"SSID must not be empty, got: {ssid!r}")

        self._runner(["nmcli", "device", "wifi", "connect", ssid, "password", psk])
