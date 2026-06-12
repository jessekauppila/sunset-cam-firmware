"""Resolve aiming-server parameters: CLI flags override device config override
defaults. lat/lng are required (the sun overlay needs them); the rest default."""
from __future__ import annotations

from sunset_cam.solstice_math import sunset_arc_azimuths

_DEFAULTS = {
    "phase": "sunset", "width": 1920,
    "mount_roll_ref_deg": -90.0, "mount_pitch_ref_deg": 0.0, "level_tol_deg": 15.0,
}

# IMX708 lens profiles: horizontal FOV (deg). The sensor is identical for both,
# so the lens can't be auto-detected from the driver — but the *needed* FOV is a
# function of latitude (the year's sunset arc widens toward the poles), so we
# auto-pick a profile from lat unless the device config overrides it.
LENS_HFOV = {"wide": 102.0, "standard": 66.0}   # 120deg-diag vs 75deg-diag IMX708


def recommended_lens(lat_deg: float, year: int = 2026) -> str:
    """Pick the lens whose FOV covers the year's sunset arc at this latitude.
    Northern (and far-southern) sites have a wider arc -> need the wide lens."""
    summer, _equinox, winter = sunset_arc_azimuths(lat_deg, year)
    span = abs(((summer - winter + 180.0) % 360.0) - 180.0)
    return "wide" if span > LENS_HFOV["standard"] else "standard"


def _resolve_hfov(pick, lat_deg: float) -> float:
    explicit = pick("hfov")          # CLI/config hfov wins
    if explicit is not None:
        return float(explicit)
    lens = pick("lens")              # then a named lens profile
    if lens in LENS_HFOV:
        return LENS_HFOV[lens]
    return LENS_HFOV[recommended_lens(lat_deg)]   # else auto-pick from latitude


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
        "hfov": _resolve_hfov(pick, float(lat)),
        "width": int(pick("width", _DEFAULTS["width"])),
        # Mount-orientation reference: cam1's IMU is fixed rotated 90deg vs a
        # landscape camera, so "level" reads roll -90 / pitch 0.
        "mount_roll_ref": float(pick("mount_roll_ref_deg", _DEFAULTS["mount_roll_ref_deg"])),
        "mount_pitch_ref": float(pick("mount_pitch_ref_deg", _DEFAULTS["mount_pitch_ref_deg"])),
        "level_tol": float(pick("level_tol_deg", _DEFAULTS["level_tol_deg"])),
    }
