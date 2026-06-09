"""The always-on device brain. Heartbeats the cloud for placement_status and
drives the camera mode. Pure decision (decide_mode) + injectable IO (run_once)
so the logic is fully testable; main() wires the real heartbeat + systemctl."""
from __future__ import annotations

import logging
import time
from typing import Callable

from sunset_cam.config import load_config
from sunset_cam.heartbeat import post_heartbeat
from sunset_cam.service_control import SystemctlController
from sunset_cam.device_config import write_location

CONFIG_PATH = "/opt/sunset-cam/config/config.json"


def decide_mode(placement_status) -> str:
    if placement_status == "awaiting_aim":
        return "aiming"
    if placement_status == "ready":
        return "capture"
    return "idle"


def run_once(status_source: Callable[[], dict], controller, config_writer) -> str:
    result = status_source()
    mode = decide_mode(result.get("placement_status"))
    if mode == "aiming" and result.get("lat") is not None and result.get("lng") is not None:
        config_writer(result["lat"], result["lng"])
    controller.set_mode(mode)
    return mode


def main(interval_s: float = 30.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s supervisor %(message)s")
    log = logging.getLogger("supervisor")
    config = load_config(CONFIG_PATH)
    controller = SystemctlController()
    log.info("supervisor up; camera_id=%s", config["camera_id"])
    while True:
        try:
            mode = run_once(
                status_source=lambda: post_heartbeat(config),
                controller=controller,
                config_writer=lambda lat, lng: write_location(CONFIG_PATH, lat, lng),
            )
            log.info("mode=%s", mode)
        except Exception as exc:  # noqa: BLE001
            log.error("loop error: %s", exc)
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
