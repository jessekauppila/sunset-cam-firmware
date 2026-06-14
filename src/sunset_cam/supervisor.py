"""The always-on device brain. Heartbeats the cloud for placement_status and
drives the camera mode. Pure decision (decide_mode) + injectable IO (run_once)
so the logic is fully testable; main() wires the real heartbeat + systemctl."""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Callable

import requests

from sunset_cam.config import load_config
from sunset_cam.heartbeat import post_heartbeat
from sunset_cam.placement_consume import decide_placement
from sunset_cam.register import post_register
from sunset_cam.service_control import SystemctlController
from sunset_cam.device_config import write_location
from sunset_cam.directive_executor import execute

CONFIG_PATH = "/opt/sunset-cam/config/config.json"


def _read_journal(unit: str, lines: int) -> str:
    """Read-only journal tail for a unit (no sudo needed for the pi user)."""
    out = subprocess.run(
        ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"],
        capture_output=True, text=True, timeout=20,
    )
    return out.stdout


def _ship_logs_to_cloud(config: dict, text: str) -> None:
    url = f"{config['api_base'].rstrip('/')}/api/cameras/{config['camera_id']}/logs"
    requests.post(
        url, json={"text": text},
        headers={"Authorization": f"Bearer {config['device_token']}"}, timeout=20,
    ).raise_for_status()


_log = logging.getLogger("supervisor")


def register_on_start(
    config: dict,
    *,
    register_fn=post_register,
    log=None,
) -> dict:
    """Call register_fn(config) once before the heartbeat loop.

    Returns the parsed registration result dict.  On any exception, logs the
    error and returns {} so the heartbeat loop is never blocked.
    """
    if log is None:
        log = _log
    try:
        return register_fn(config)
    except Exception as exc:  # noqa: BLE001
        log.error("register on start failed: %s", exc)
        return {}


def online_placement_decision(parsed: dict):
    """Map a parsed heartbeat to (mode, placement_verb).

    mode drives set_mode (idle|aiming|capture as today); placement_verb is
    the coarse-vs-precise verb from decide_placement, used to enable on-device
    sun self-refine when coarse.
    """
    mode = decide_mode(parsed.get("placement_status"))
    verb = decide_placement(parsed).verb
    return mode, verb


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


def run_directives(directives, execute_fn: Callable[[dict], dict], seen_ids: set) -> list:
    """Execute each not-yet-seen directive once and collect its result. seen_ids is
    mutated to make execution idempotent across polls; results report on the next
    heartbeat. execute_fn never raises (it returns a 'failed' result), so one bad
    directive does not stop the others or the loop."""
    results = []
    for d in directives or []:
        did = d.get("id")
        if did in seen_ids:
            continue
        seen_ids.add(did)
        results.append(execute_fn(d))
    return results


def main(interval_s: float = 30.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s supervisor %(message)s")
    log = logging.getLogger("supervisor")
    config = load_config(CONFIG_PATH)
    controller = SystemctlController()
    log.info("supervisor up; camera_id=%s", config["camera_id"])
    seen_ids: set = set()
    pending_results: list = []
    execute_fn = lambda d: execute(
        d, log_sink=lambda text: _ship_logs_to_cloud(config, text), journal_reader=_read_journal,
    )
    register_on_start(config, log=log)
    while True:
        try:
            # one heartbeat carries last cycle's results up and the next directives down
            result = post_heartbeat(config, results=pending_results)
            mode, verb = online_placement_decision(result)
            run_once(
                status_source=lambda: result,
                controller=controller,
                config_writer=lambda lat, lng: write_location(CONFIG_PATH, lat, lng),
            )
            log.info("mode=%s placement_verb=%s", mode, verb)
            if verb == "SUN_SELF_REFINE":
                log.info("enabling sun self-refine")
            pending_results = run_directives(result.get("directives"), execute_fn, seen_ids)
            for r in pending_results:
                log.info("directive %s -> %s", r.get("id"), r.get("status"))
        except Exception as exc:  # noqa: BLE001
            log.error("loop error: %s", exc)
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
