#!/usr/bin/env bash
# firstboot.sh — Runs ONCE on first boot via sunset-cam-firstboot.service,
# then self-disables so it never runs again.
#
# Purpose: ensure the device-token and placement storage dirs exist with safe
# permissions before any other service tries to write to them.
#
# ⚠️  HARDWARE-GATED: this script runs on the Pi as root.
#   Paths must match what cloud_client.py (DEVICE_TOKEN_PATH) and
#   placement_consume.py (PLACEMENT_PATH) use: /etc/sunset-cam/
set -euo pipefail

# Create the secure config dir for device token + placement data.
install -d -m 700 /etc/sunset-cam

# Touch the placement file so readers don't 404 before first heartbeat.
touch /etc/sunset-cam/placement.json || true
chmod 600 /etc/sunset-cam/placement.json || true

# Self-disable: this service must never run again on subsequent boots.
systemctl disable sunset-cam-firstboot.service

echo "[firstboot] done — /etc/sunset-cam created, service disabled"
