"""Content-sanity tests for hardware-gated SETUP-stack config + systemd files.

These tests do NOT test runtime behavior (that requires a real Pi with hostapd,
dnsmasq, and a radio). They verify that key lines are present in each file so
that a typo or accidental deletion is caught before hardware bring-up.

⚠️  HARDWARE-GATED: the actual AP, DHCP, DNS, and Flask behavior must be
validated manually on a Pi Zero 2 W. See:
  docs/hardware/2026-06-14-wifi-onboarding-bringup-runbook.md
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


# ── hostapd.conf ────────────────────────────────────────────────────────────

def test_hostapd_conf_has_wlan0_interface():
    assert "interface=wlan0" in _read("config/hostapd.conf")


def test_hostapd_conf_has_ssid_template_with_xxxx_placeholder():
    text = _read("config/hostapd.conf")
    # ExecStartPre in sunset-cam-setup.service substitutes XXXX at boot.
    assert "ssid=Sunset-Cam-XXXX" in text


def test_hostapd_conf_is_open_network_no_wpa_key():
    text = _read("config/hostapd.conf")
    # Must be an OPEN AP: no active wpa= directive. Comments are fine.
    active_lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
    assert not any(l.startswith("wpa=") for l in active_lines), (
        "hostapd.conf must NOT have an active wpa= line — this AP must be open"
    )


# ── dnsmasq-setup.conf ──────────────────────────────────────────────────────

def test_dnsmasq_conf_has_wlan0_interface():
    assert "interface=wlan0" in _read("config/dnsmasq-setup.conf")


def test_dnsmasq_conf_has_dhcp_range_in_expected_subnet():
    # dhcp-range must be in the 10.42.0.x/24 subnet matching the AP IP.
    assert "dhcp-range=10.42.0.50,10.42.0.150" in _read("config/dnsmasq-setup.conf")


def test_dnsmasq_conf_hijacks_all_dns_to_ap_ip():
    # address=/#/10.42.0.1 resolves every query to the device so iOS/Android
    # captive-portal probes automatically pop the browser sheet.
    assert "address=/#/10.42.0.1" in _read("config/dnsmasq-setup.conf")


# ── sunset-cam-setup.service ────────────────────────────────────────────────

def test_setup_service_conflicts_with_supervisor_and_capture():
    text = _read("systemd/sunset-cam-setup.service")
    assert "Conflicts=" in text
    assert "sunset-cam.service" in text
    assert "sunset-cam-supervisor.service" in text


def test_setup_service_runs_the_flask_portal_entrypoint():
    assert "run-setup-app.py" in _read("systemd/sunset-cam-setup.service")


def test_setup_service_has_mac_suffix_substition_in_execstartpre():
    text = _read("systemd/sunset-cam-setup.service")
    # ExecStartPre must substitute the XXXX MAC suffix into the AP SSID.
    assert "Sunset-Cam-" in text
    assert "MAC" in text  # the shell variable that holds the suffix


def test_setup_service_assigns_static_ap_ip():
    text = _read("systemd/sunset-cam-setup.service")
    assert "10.42.0.1" in text


# ── sunset-cam-boot.service ─────────────────────────────────────────────────

def test_boot_service_is_oneshot():
    assert "Type=oneshot" in _read("systemd/sunset-cam-boot.service")


def test_boot_service_runs_the_boot_module():
    text = _read("systemd/sunset-cam-boot.service")
    assert "sunset_cam.boot" in text


def test_boot_service_wanted_by_multi_user():
    assert "WantedBy=multi-user.target" in _read("systemd/sunset-cam-boot.service")


# ── scripts/firstboot.sh ────────────────────────────────────────────────────

def test_firstboot_script_creates_sunset_cam_dir():
    assert "/etc/sunset-cam" in _read("scripts/firstboot.sh")


def test_firstboot_script_self_disables():
    assert "systemctl disable sunset-cam-firstboot" in _read("scripts/firstboot.sh")


def test_firstboot_script_has_set_euo_pipefail():
    # Safety: must not silently swallow errors on first boot.
    assert "set -euo pipefail" in _read("scripts/firstboot.sh")
