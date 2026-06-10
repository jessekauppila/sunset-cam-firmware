"""Resolve aiming-server parameters: CLI flags override device config override
defaults. lat/lng are required (the sun overlay needs them); the rest default."""
from __future__ import annotations

_DEFAULTS = {
    "phase": "sunset", "hfov": 102.0, "width": 1920,
    "mount_roll_ref_deg": -90.0, "mount_pitch_ref_deg": 0.0, "level_tol_deg": 15.0,
}


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
    # JSON config / cloud payloads may carry these as strings; the aiming server
    # feeds lat/lng into math.radians(), so coerce to real numbers here.
    return {
        "lat": float(lat), "lng": float(lng),
        "phase": pick("phase", _DEFAULTS["phase"]),
        "hfov": float(pick("hfov", _DEFAULTS["hfov"])),
        "width": int(pick("width", _DEFAULTS["width"])),
        # Mount-orientation reference: cam1's IMU is fixed rotated 90deg vs a
        # landscape camera, so "level" reads roll -90 / pitch 0.
        "mount_roll_ref": float(pick("mount_roll_ref_deg", _DEFAULTS["mount_roll_ref_deg"])),
        "mount_pitch_ref": float(pick("mount_pitch_ref_deg", _DEFAULTS["mount_pitch_ref_deg"])),
        "level_tol": float(pick("level_tol_deg", _DEFAULTS["level_tol_deg"])),
    }
