"""Content-sanity tests for hardware-gated SETUP-stack config + systemd files.

These tests do NOT test runtime behavior (that requires a real Pi with a radio
and NetworkManager). They verify that key lines are present in each file so
that a typo or accidental deletion is caught before hardware bring-up.

⚠️  HARDWARE-GATED: the actual AP, DHCP, and Flask behavior must be validated
manually on a Pi Zero 2 W. See:
  docs/hardware/2026-06-14-wifi-onboarding-bringup-runbook.md
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


# ── scripts/setup-ap.sh ─────────────────────────────────────────────────────

def test_setup_ap_script_exists():
    assert (ROOT / "scripts/setup-ap.sh").exists(), (
        "scripts/setup-ap.sh must exist — it is the NM-native AP bring-up script"
    )


def test_setup_ap_script_is_wpa2_ap_shared_mode():
    text = _read("scripts/setup-ap.sh")
    assert "802-11-wireless.mode ap" in text, (
        "setup-ap.sh must set 802-11-wireless.mode ap (NM hotspot mode)"
    )
    assert "ipv4.method shared" in text, (
        "setup-ap.sh must set ipv4.method shared (NM provides DHCP + gateway)"
    )
    assert "wpa-psk" in text, (
        "setup-ap.sh must set 802-11-wireless-security.key-mgmt wpa-psk (WPA2)"
    )
    assert "SETUP_AP_PASSWORD" in text, (
        "setup-ap.sh must reference SETUP_AP_PASSWORD for the WPA2 passphrase"
    )


def test_setup_ap_script_has_default_password_constant():
    text = _read("scripts/setup-ap.sh")
    # Default password must be in the script and >= 8 chars (WPA2 minimum)
    assert 'SETUP_AP_PASSWORD="${SETUP_AP_PASSWORD:-sunsetcam}"' in text, (
        "setup-ap.sh must define SETUP_AP_PASSWORD with default 'sunsetcam'"
    )


def test_setup_ap_script_has_up_and_down_commands():
    text = _read("scripts/setup-ap.sh")
    assert "up)" in text, "setup-ap.sh must handle the 'up' argument"
    assert "down)" in text, "setup-ap.sh must handle the 'down' argument"


def test_setup_ap_script_embeds_mac_suffix_in_ssid():
    text = _read("scripts/setup-ap.sh")
    # The SSID is built with a mac_suffix function call so each unit is unique.
    assert "mac_suffix" in text, (
        "setup-ap.sh must use a mac_suffix function to build a unique SSID"
    )
    assert "Sunset-Cam-" in text, (
        "setup-ap.sh SSID must start with 'Sunset-Cam-'"
    )


def test_setup_ap_script_does_not_reference_hostapd_or_dnsmasq():
    text = _read("scripts/setup-ap.sh")
    assert "hostapd" not in text, "setup-ap.sh must not reference hostapd"
    assert "dnsmasq" not in text, "setup-ap.sh must not reference dnsmasq"


# ── systemd/sunset-cam-setup.service ────────────────────────────────────────

def test_setup_service_conflicts_with_supervisor_and_capture():
    text = _read("systemd/sunset-cam-setup.service")
    assert "Conflicts=" in text
    assert "sunset-cam.service" in text
    assert "sunset-cam-supervisor.service" in text


def test_setup_service_runs_the_flask_portal_entrypoint():
    assert "run-setup-app.py" in _read("systemd/sunset-cam-setup.service")


def test_setup_service_references_setup_ap_script():
    text = _read("systemd/sunset-cam-setup.service")
    assert "setup-ap.sh" in text, (
        "sunset-cam-setup.service must call setup-ap.sh for AP bring-up/teardown"
    )


def test_setup_service_does_not_reference_hostapd_or_dnsmasq():
    text = _read("systemd/sunset-cam-setup.service")
    assert "hostapd" not in text, (
        "sunset-cam-setup.service must not reference hostapd — use NM hotspot"
    )
    assert "dnsmasq" not in text, (
        "sunset-cam-setup.service must not reference dnsmasq — NM shared mode "
        "provides DHCP automatically"
    )


def test_setup_service_has_execstartpre_up_and_execstoppost_down():
    text = _read("systemd/sunset-cam-setup.service")
    assert "ExecStartPre=" in text and "setup-ap.sh up" in text, (
        "service must call setup-ap.sh up in ExecStartPre"
    )
    assert "ExecStopPost=" in text and "setup-ap.sh down" in text, (
        "service must call setup-ap.sh down in ExecStopPost"
    )


# ── sunset-cam-boot.service ─────────────────────────────────────────────────

def test_boot_service_is_oneshot():
    assert "Type=oneshot" in _read("systemd/sunset-cam-boot.service")


def test_boot_service_runs_the_boot_module():
    text = _read("systemd/sunset-cam-boot.service")
    assert "sunset_cam.boot" in text


def test_boot_service_wanted_by_multi_user():
    assert "WantedBy=multi-user.target" in _read("systemd/sunset-cam-boot.service")


def test_boot_service_waits_for_network_online():
    # Must order after network-online.target — NetworkManager merely *started*
    # isn't enough (nmcli returns no creds before NM settles → false SETUP).
    text = _read("systemd/sunset-cam-boot.service")
    assert "After=network-online.target" in text
    assert "Wants=network-online.target" in text


# ── scripts/firstboot.sh ────────────────────────────────────────────────────

def test_firstboot_script_creates_config_dir():
    # The firmware reads /opt/sunset-cam/config/config.json (supervisor CONFIG_PATH).
    assert "/opt/sunset-cam/config" in _read("scripts/firstboot.sh")


def test_firstboot_script_self_disables():
    assert "systemctl disable sunset-cam-firstboot" in _read("scripts/firstboot.sh")


def test_firstboot_script_has_set_euo_pipefail():
    # Safety: must not silently swallow errors on first boot.
    assert "set -euo pipefail" in _read("scripts/firstboot.sh")
