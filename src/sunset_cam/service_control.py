"""Drive the two camera systemd units by mode. Idempotent at the systemd level
(starting a running unit / stopping a stopped unit are no-ops), so set_mode is
safe to call every loop. The runner is injectable for tests."""
from __future__ import annotations

import subprocess
from typing import Callable

AIMING_UNIT = "sunset-cam-aiming.service"
CAPTURE_UNIT = "sunset-cam.service"


def _default_runner(args: list) -> None:
    subprocess.run(["systemctl", *args], check=False)


class SystemctlController:
    def __init__(self, runner: Callable[[list], None] = _default_runner) -> None:
        self._run = runner

    def set_mode(self, mode: str) -> None:
        if mode == "aiming":
            self._run(["stop", CAPTURE_UNIT])
            self._run(["start", AIMING_UNIT])
        elif mode == "capture":
            self._run(["stop", AIMING_UNIT])
            self._run(["start", CAPTURE_UNIT])
        else:  # idle / unknown
            self._run(["stop", AIMING_UNIT])
            self._run(["stop", CAPTURE_UNIT])
