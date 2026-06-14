"""Placement consumer: translate a parsed heartbeat placement dict into an
action verb the supervisor can act on.

Verbs
-----
AWAIT           — placement not yet ready (awaiting_location, awaiting_aim, …)
SUN_SELF_REFINE — ready but coarse (bracket-derived heading); run on-device
                  sun-track refine to upgrade the azimuth before capturing.
LEGACY_PRECISE  — ready and already-precise (sun-calibrated or manually set);
                  no refine step required.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PlacementDecision:
    verb: str
    placement: dict


def decide_placement(parsed: dict) -> PlacementDecision:
    """Decide what the supervisor should do given a parsed placement dict.

    Args:
        parsed: the dict returned by :func:`~sunset_cam.heartbeat.parse_placement`.

    Returns:
        A :class:`PlacementDecision` whose ``verb`` is one of ``AWAIT``,
        ``SUN_SELF_REFINE``, or ``LEGACY_PRECISE``.
    """
    if parsed.get("placement_status") != "ready":
        return PlacementDecision("AWAIT", parsed)
    if parsed.get("coarse") is True:
        return PlacementDecision("SUN_SELF_REFINE", parsed)
    return PlacementDecision("LEGACY_PRECISE", parsed)
