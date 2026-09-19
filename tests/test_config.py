import json
from pathlib import Path

import pytest

from sunset_cam.config import load_config, load_identity, ConfigError


def write_cfg(tmp_path: Path, overrides: dict | None = None) -> Path:
    base = {
        "camera_id": 42,
        "device_token": "abcd" * 16,
        "api_base": "https://sunrisesunset.studio",
        "phase": "sunset",
        "window_id": "2026-05-03-sunset-cam42",
        "capture_window_start_utc": "2026-05-03T01:00:00Z",
        "capture_window_end_utc": "2026-05-03T02:30:00Z",
        "capture_interval_s": 1.0,
    }
    if overrides:
        base.update(overrides)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(base))
    return p


def test_load_identity_accepts_identity_only_config(tmp_path: Path) -> None:
    # A freshly-provisioned device: identity only, NO capture config.
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "claim_code": "SUNSET-AAAA-BBBB",
        "camera_id": 2,
        "device_token": "tok-xyz",
        "api_base": "https://sunrisesunset.studio",
        "hardware_id": "hw-sunset-cam-2",
    }))
    cfg = load_identity(p)
    assert cfg["camera_id"] == 2
    assert cfg["device_token"] == "tok-xyz"
    assert cfg["api_base"] == "https://sunrisesunset.studio"
    assert cfg["log_level"] == "INFO"  # defaulted


def test_load_identity_rejects_missing_identity_key(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"camera_id": 2, "api_base": "https://x"}))  # no device_token
    with pytest.raises(ConfigError):
        load_identity(p)


def test_load_identity_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_identity(tmp_path / "nope.json")


def test_load_identity_also_works_on_a_full_capture_config(tmp_path: Path) -> None:
    # The full config is a superset of identity, so load_identity accepts it too.
    cfg = load_identity(write_cfg(tmp_path))
    assert cfg["camera_id"] == 42


def test_load_config_returns_typed_dict(tmp_path: Path) -> None:
    cfg = load_config(write_cfg(tmp_path))
    assert cfg["camera_id"] == 42
    assert cfg["api_base"] == "https://sunrisesunset.studio"
    assert cfg["capture_interval_s"] == 1.0


def test_load_config_rejects_missing_keys(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"camera_id": 42}))
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_config_rejects_bad_phase(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(write_cfg(tmp_path, {"phase": "noon"}))


def test_load_config_rejects_non_iso_window(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            write_cfg(tmp_path, {"capture_window_start_utc": "yesterday"})
        )


# --- profiles -----------------------------------------------------------------


def cloud_cfg() -> dict:
    return {
        "camera_id": 7,
        "profiles": [
            {
                "name": "clouds",
                "window": {"daily_utc": {"start": "16:00", "end": "01:00"}},
                "interval_s": 300,
                "sink": {"kind": "welkin", "url": "http://192.168.1.20:8000"},
            }
        ],
    }


def test_load_config_accepts_a_cloud_only_profiles_config(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cloud_cfg()))
    cfg = load_config(p)
    assert cfg["camera_id"] == 7
    assert cfg["log_level"] == "INFO"


def test_load_config_turns_profile_errors_into_config_errors(tmp_path: Path) -> None:
    bad = cloud_cfg()
    bad["profiles"][0]["interval_s"] = -1
    p = tmp_path / "config.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ConfigError, match="interval_s"):
        load_config(p)


def test_load_config_with_profiles_still_needs_camera_id(tmp_path: Path) -> None:
    bad = cloud_cfg()
    del bad["camera_id"]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ConfigError, match="camera_id"):
        load_config(p)


def test_validator_cli_reports_ok_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from sunset_cam.config import check_main

    good = tmp_path / "good.json"
    good.write_text(json.dumps(cloud_cfg()))
    assert check_main([str(good)]) == 0
    assert "clouds" in capsys.readouterr().out

    bad_cfg = cloud_cfg()
    bad_cfg["profiles"][0]["sink"] = {"kind": "welkin"}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_cfg))
    assert check_main([str(bad)]) == 1
    assert "url" in capsys.readouterr().err
