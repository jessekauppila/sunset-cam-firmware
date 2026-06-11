"""Execute control-plane directives pulled from a heartbeat response.

Side effects (reading the journal, shipping the text to the cloud) are injected,
so the dispatch logic is pure and unit-testable and the device wiring stays thin.
Slice 1 handles one safe verb: ``ship-logs`` (read-only, no sudo). Add
``restart`` / ``update`` later once a scoped sudoers rule exists.
"""
from __future__ import annotations

from typing import Callable


def _ship_logs(directive: dict, *, log_sink: Callable, journal_reader: Callable) -> str:
    payload = directive.get("payload") or {}
    unit = payload.get("unit", "sunset-cam")
    lines = int(payload.get("lines", 200))
    text = journal_reader(unit, lines)
    log_sink(text)
    return f"shipped {lines} lines of {unit}"


_HANDLERS = {"ship-logs": _ship_logs}


def execute(directive: dict, *, log_sink: Callable, journal_reader: Callable) -> dict:
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
        detail = handler(directive, log_sink=log_sink, journal_reader=journal_reader)
        return {"id": did, "status": "done", "detail": detail}
    except Exception as exc:  # noqa: BLE001 — report, never crash the loop
        return {"id": did, "status": "failed", "detail": str(exc)}
