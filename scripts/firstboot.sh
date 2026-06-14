#!/usr/bin/env bash
# firstboot.sh — Runs ONCE on first boot via sunset-cam-firstboot.service,
# then self-disables so it never runs again.
#
# Purpose: ensure the config dir exists with safe permissions before any other
# service tries to read/write config.json (the device identity + placement the
# supervisor and capture loop read from /opt/sunset-cam/config/config.json).
#
# ⚠️  HARDWARE-GATED: this script runs on the Pi as root.
set -euo pipefail

# The config dir the firmware reads (supervisor CONFIG_PATH, capture, aiming all
# use /opt/sunset-cam/config/config.json). Provisioning writes config.json here.
install -d -m 755 /opt/sunset-cam/config

# Self-disable: this service must never run again on subsequent boots.
systemctl disable sunset-cam-firstboot.service

echo "[firstboot] done — /opt/sunset-cam/config ensured, service disabled"
