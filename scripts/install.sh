#!/usr/bin/env bash
# Idempotent installer for a fresh Raspberry Pi OS Lite system.
# Run via: curl -sSL <raw url> | bash, or after `git clone /opt/sunset-cam`.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/sunset-cam}"

echo "==> apt deps"
sudo apt update
sudo apt install -y python3-picamera2 python3-venv git

echo "==> venv at $REPO_DIR/.venv"
if [[ ! -d "$REPO_DIR/.venv" ]]; then
  python3 -m venv --system-site-packages "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
"$REPO_DIR/.venv/bin/pip" install -e "$REPO_DIR"

echo "==> systemd unit"
sudo cp "$REPO_DIR/systemd/sunset-cam.service" /etc/systemd/system/sunset-cam.service
sudo systemctl daemon-reload

if [[ ! -f "$REPO_DIR/config/config.json" ]]; then
  echo "==> NOTE: $REPO_DIR/config/config.json does not exist."
  echo "    Copy config/config.example.json there and fill in"
  echo "    camera_id, device_token, api_base, capture_window_*."
  echo "    Then: sudo systemctl enable --now sunset-cam"
else
  sudo systemctl enable --now sunset-cam
  # If the service is already running, pick up any unit-file edits
  # immediately rather than waiting for next reboot.
  if sudo systemctl is-active --quiet sunset-cam; then
    sudo systemctl restart sunset-cam
  fi
  echo "==> started; tail logs with: journalctl -u sunset-cam -f"
fi
