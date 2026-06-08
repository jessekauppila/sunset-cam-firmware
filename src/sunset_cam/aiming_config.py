"""Resolve aiming-server parameters: CLI flags override device config override
defaults. lat/lng are required (the sun overlay needs them); the rest default."""
from __future__ import annotations

_DEFAULTS = {"phase": "sunset", "hfov": 102.0, "width": 1920}


def resolve_aiming_params(cli: dict, config: dict) -> dict:
    def pick(key, default=None):
        v = cli.get(key)
        if v is not None:
            return v
        v = config.get(key)
        if v is not None:
            return v
        return default

    lat, lng = pick("lat"), pick("lng")
    if lat is None or lng is None:
        raise ValueError("lat/lng must be provided via CLI flags or device config")
    return {
        "lat": lat, "lng": lng,
        "phase": pick("phase", _DEFAULTS["phase"]),
        "hfov": pick("hfov", _DEFAULTS["hfov"]),
        "width": pick("width", _DEFAULTS["width"]),
    }
