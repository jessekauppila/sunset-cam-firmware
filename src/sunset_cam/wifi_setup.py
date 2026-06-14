"""Write wpa_supplicant credentials and trigger a WiFi join.

Subprocess and file path are injected so the class is fully testable without
any real hardware or wpa_cli present.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


def _default_runner(args: list) -> None:
    subprocess.run(args, check=True, timeout=30)


class WifiSetupService:
    """Write wpa_supplicant network creds and (re)associate with the AP.

    Parameters
    ----------
    wpa_path:
        Filesystem path for the wpa_supplicant.conf to write.
    runner:
        Callable that receives a list of args and executes them (defaults to
        ``subprocess.run``). Inject a mock in tests to avoid real wpa_cli calls.
    """

    def __init__(
        self,
        wpa_path: str,
        runner: Callable[[list], None] = _default_runner,
    ) -> None:
        self._wpa_path = wpa_path
        self._runner = runner

    def write_credentials(self, ssid: str, psk: str) -> None:
        """Write a minimal valid wpa_supplicant.conf with a network block.

        Raises
        ------
        ValueError
            When *ssid* is empty or whitespace-only.
        """
        if not ssid or not ssid.strip():
            raise ValueError(f"SSID must not be empty, got: {ssid!r}")

        safe_ssid = ssid.replace('"', '\\"')
        safe_psk = psk.replace('"', '\\"')

        content = (
            "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
            "country=US\n"
            "update_config=1\n"
            "\n"
            "network={\n"
            f'\tssid="{safe_ssid}"\n'
            f'\tpsk="{safe_psk}"\n'
            "}\n"
        )

        Path(self._wpa_path).write_text(content)

    def join(self) -> None:
        """Ask wpa_supplicant to re-read credentials and (re)associate.

        Uses the injected runner — no real wpa_cli call fires in tests.
        """
        self._runner(["wpa_cli", "-i", "wlan0", "reconfigure"])
