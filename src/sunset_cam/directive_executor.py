"""Execute control-plane directives pulled from a heartbeat response.

Side effects (reading the journal, shipping the text to the cloud, wiping
WiFi credentials) are injected, so the dispatch logic is pure and unit-testable
and the device wiring stays thin.

Slice 1 handles one safe verb: ``ship-logs`` (read-only, no sudo).
Slice C adds: ``wipe_wifi`` (delete NM WiFi connection profiles; device re-enters SETUP).
Add ``restart`` / ``update`` later once a scoped sudoers rule exists.
"""
from __future__ import annotations

from typing import Callable


def _ship_logs(directive: dict, **deps) -> str:
    log_sink = deps["log_sink"]
    journal_reader = deps["journal_reader"]
    payload = directive.get("payload") or {}
    unit = payload.get("unit", "sunset-cam")
    lines = int(payload.get("lines", 200))
    text = journal_reader(unit, lines)
    log_sink(text)
    return f"shipped {lines} lines of {unit}"


def _wipe_wifi(directive: dict, **deps) -> str:
    wifi_wiper = deps["wifi_wiper"]
    wifi_wiper()  # delete/blank the wpa creds file; device re-enters SETUP next boot
    return "wifi credentials wiped; will re-enter setup on next boot"


_HANDLERS = {"ship-logs": _ship_logs, "wipe_wifi": _wipe_wifi}


def execute(
    directive: dict,
    *,
    log_sink: Callable = None,
    journal_reader: Callable = None,
    wifi_wiper: Callable = None,
) -> dict:
    """Run one directive; return a result {id, status, detail}.

    status is ``done`` on success, ``failed`` on an unknown type or any handler
    error (the detail carries the reason). Never raises — a bad directive must
    not take down the heartbeat loop.
    """
    did = directive.get("id")
    dtype = directive.get("type")
    handler = _HANDLERS.get(dtype)
    if handler is None:
        return {"id": did, "status": "failed", "detail": f"unknown directive type: {dtype}"}
    try:
        detail = handler(
            directive,
            log_sink=log_sink,
            journal_reader=journal_reader,
            wifi_wiper=wifi_wiper,
        )
        return {"id": did, "status": "done", "detail": detail}
    except Exception as exc:  # noqa: BLE001 — report, never crash the loop
        return {"id": did, "status": "failed", "detail": str(exc)}
