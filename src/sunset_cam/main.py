"""Entry point. Run with: python -m sunset_cam.main /etc/sunset-cam/config.json"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sunset_cam.config import load_config
from sunset_cam.window import is_active_now
from sunset_cam.upload import upload_snapshot


_running = True


def _handle_sigterm(_signum: int, _frame: object) -> None:
    global _running
    _running = False


def run(config_path: str | Path) -> int:
    config = load_config(config_path)

    logging.basicConfig(
        level=getattr(logging, config["log_level"], logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("sunset_cam")
    log.info("starting; camera_id=%s api_base=%s", config["camera_id"], config["api_base"])

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    interval = float(config["capture_interval_s"])

    while _running:
        now = datetime.now(timezone.utc)
        if not is_active_now(config, now):
            log.debug("outside window; sleeping %.2fs", interval)
            time.sleep(interval)
            continue

        try:
            from sunset_cam.capture import capture_jpeg

            jpeg = capture_jpeg()
        except Exception as exc:  # noqa: BLE001
            log.error("capture failed: %s", exc)
            time.sleep(interval)
            continue

        try:
            ack = upload_snapshot(config, jpeg, now)
            log.info(
                "uploaded snapshot_id=%s bytes=%d", ack["snapshot_id"], len(jpeg)
            )
        except Exception as exc:  # noqa: BLE001
            log.error("upload failed: %s", exc)

        time.sleep(interval)

    log.info("shutdown signal received; exiting cleanly")
    try:
        from sunset_cam.capture import shutdown

        shutdown()
    except Exception:  # noqa: BLE001
        pass
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m sunset_cam.main /path/to/config.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1]))


if __name__ == "__main__":
    main()
