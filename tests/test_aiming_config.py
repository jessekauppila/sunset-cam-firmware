import pytest
from sunset_cam.aiming_config import resolve_aiming_params

def test_cli_overrides_config_and_defaults():
    out = resolve_aiming_params(
        cli={"lat": 1.0, "lng": 2.0, "phase": None, "hfov": None, "width": None},
        config={"lat": 9.0, "lng": 9.0, "phase": "sunrise", "hfov": 90.0, "width": 1280},
    )
    assert out == {"lat": 1.0, "lng": 2.0, "phase": "sunrise", "hfov": 90.0, "width": 1280}

def test_config_used_when_cli_absent():
    out = resolve_aiming_params(
        cli={"lat": None, "lng": None, "phase": None, "hfov": None, "width": None},
        config={"lat": 48.7519, "lng": -122.4787},
    )
    assert out["lat"] == 48.7519 and out["lng"] == -122.4787
    assert out["phase"] == "sunset" and out["hfov"] == 102.0 and out["width"] == 1920

def test_missing_lat_lng_raises():
    with pytest.raises(ValueError):
        resolve_aiming_params(cli={"lat": None, "lng": None}, config={})

def test_string_coords_from_config_coerced_to_numbers():
    # config.json (and the cloud heartbeat) can deliver lat/lng/hfov/width as strings;
    # the aiming server feeds them straight into math.radians(), so they must be numeric.
    out = resolve_aiming_params(
        cli={"lat": None, "lng": None, "phase": None, "hfov": None, "width": None},
        config={"lat": "48.7519", "lng": "-122.4787", "hfov": "102", "width": "1920"},
    )
    assert out["lat"] == 48.7519 and isinstance(out["lat"], float)
    assert out["lng"] == -122.4787 and isinstance(out["lng"], float)
    assert out["hfov"] == 102.0 and isinstance(out["hfov"], float)
    assert out["width"] == 1920 and isinstance(out["width"], int)
