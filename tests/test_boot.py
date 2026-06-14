"""Tests for boot-time SETUP vs ONLINE decision logic."""
from __future__ import annotations


def test_missing_file_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    assert has_wifi_credentials(str(tmp_path / "nope.conf")) is False


def test_file_with_network_block_is_true(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"
    p.write_text('ctrl_interface=...\nnetwork={\n ssid="x"\n psk="y"\n}\n')
    assert has_wifi_credentials(str(p)) is True


def test_file_without_network_block_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"
    p.write_text("ctrl_interface=/run/wpa\n")
    assert has_wifi_credentials(str(p)) is False
