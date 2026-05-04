import json
from pathlib import Path

import pytest

from sunset_cam.config import load_config, ConfigError


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
