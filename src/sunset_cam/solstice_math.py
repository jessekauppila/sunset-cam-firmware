"""Sun azimuth + sunsets-per-year computation, server-side.

Pure math, no I/O, no external deps beyond stdlib. Uses NOAA's solar
position approximation good to roughly ±0.5° for civil purposes — accurate
enough for placement advice; not survey-grade.

References:
- NOAA Solar Calculator: https://gml.noaa.gov/grad/solcalc/
- Equations (Spencer 1971 / Reda+Andreas refined) for declination + equation of time

Accuracy: Computes the geometric sunset azimuth (sun's center on the
mathematical horizon). Real-world apparent sunset includes ~0.6° of
atmospheric refraction + horizon dip, which lifts the apparent sunset
position by a few degrees of azimuth at mid-to-high latitudes. The
discrepancy is ~3–5° near the solstices at 48° latitude. For the v1
goal (~102° FOV camera placement guidance), this approximation is
sufficient — the wedge between solstice markers will be off by a few
pixels at most, well within usability.
"""
from __future__ import annotations

import math
from datetime import date, timedelta


def _julian_day(year: int, month: int, day: int) -> float:
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day + b - 1524.5
    )


def _solar_declination_deg(jd: float) -> float:
    """Approximate solar declination, NOAA Spencer formula."""
    n = jd - 2451545.0  # days since J2000.0
    g_rad = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam_rad = math.radians(
        (280.460 + 0.9856474 * n + 1.915 * math.sin(g_rad) + 0.020 * math.sin(2 * g_rad))
        % 360.0
    )
    eps_rad = math.radians(23.439 - 0.0000004 * n)
    decl_rad = math.asin(math.sin(eps_rad) * math.sin(lam_rad))
    return math.degrees(decl_rad)


def sunset_azimuth_for_day(lat_deg: float, year: int, month: int, day: int) -> float:
    """Approximate azimuth (degrees from North, clockwise) of the sun at sunset
    on the given date at the given latitude.

    At sunset (altitude = 0) the azimuth simplifies to:
        A = arccos(sin(δ) / cos(φ))          [angle from north toward west]
        compass = 360° − A                    [sunset is always westward]

    This is equivalent to the NOAA formula. Good to ±1° for civil purposes.
    """
    jd = _julian_day(year, month, day) + 0.5  # noon UT
    decl_deg = _solar_declination_deg(jd)
    decl_rad = math.radians(decl_deg)
    lat_rad = math.radians(lat_deg)

    # cos of the angle from geographic north (measured toward the west at sunset).
    cos_az = math.sin(decl_rad) / math.cos(lat_rad)
    cos_az = max(-1.0, min(1.0, cos_az))
    az_from_north_deg = math.degrees(math.acos(cos_az))
    # Sunset is toward the west, so compass bearing = 360 - az_from_north.
    return (360.0 - az_from_north_deg) % 360.0


def compute_sun_azimuth(lat_deg: float, lng_deg: float, t_utc) -> float:
    """Azimuth (degrees from North, clockwise) of the sun at time t_utc (a
    timezone-aware UTC datetime) seen from (lat, lng). NOAA approximation,
    good to ~+/-1 degree. Reuses the declination model used elsewhere here."""
    jd = _julian_day(t_utc.year, t_utc.month, t_utc.day)
    n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = math.radians(
        (280.460 + 0.9856474 * n + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0
    )
    eps = math.radians(23.439 - 0.0000004 * n)
    decl = math.asin(math.sin(eps) * math.sin(lam))

    ra_deg = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0
    l_mean = (280.460 + 0.9856474 * n) % 360.0
    eot_min = 4.0 * (((l_mean - ra_deg + 180.0) % 360.0) - 180.0)

    minutes_utc = t_utc.hour * 60.0 + t_utc.minute + t_utc.second / 60.0
    true_solar_min = (minutes_utc + eot_min + 4.0 * lng_deg) % 1440.0
    hour_angle = math.radians(true_solar_min / 4.0 - 180.0)

    phi = math.radians(lat_deg)
    gamma = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(phi) - math.tan(decl) * math.cos(phi),
    )
    return (math.degrees(gamma) + 180.0) % 360.0


def az_to_pixel(
    az_deg: float, center_az: float, fov_deg: float, screen_width: int
) -> float:
    """Map an azimuth to a horizontal pixel coordinate on the preview frame.

    Returns the screen x in the half-open range corresponding to the camera's
    FOV. Values outside the FOV map outside [0, screen_width].
    """
    # Signed delta in [-180, 180]
    delta = ((az_deg - center_az + 540.0) % 360.0) - 180.0
    return screen_width * (0.5 + delta / fov_deg)


def count_sunsets_in_fov(
    lat_deg: float, lng_deg: float,
    center_az: float, fov_deg: float,
    year: int,
) -> int:
    """Count days in the given year where the sunset azimuth at (lat,lng)
    falls within the camera's horizontal field-of-view centered on center_az."""
    half_fov = fov_deg / 2.0
    count = 0
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        az = sunset_azimuth_for_day(lat_deg, d.year, d.month, d.day)
        delta = ((az - center_az + 540.0) % 360.0) - 180.0
        if -half_fov <= delta <= half_fov:
            count += 1
        d += timedelta(days=1)
    return count
