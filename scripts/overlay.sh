#!/usr/bin/env bash
# overlay.sh — toggle the read-only overlay filesystem ("unplug-safe" mode).
#
# With the overlay ON, the SD card is mounted read-only and all writes go to a
# RAM overlay discarded on reboot — so pulling power can never corrupt the card.
# That's the production/shipped state. Turn it OFF only for a maintenance window
# (firmware/OS update), then back ON.
#
# Usage:
#   sudo bash scripts/overlay.sh status
#   sudo bash scripts/overlay.sh on       # enable read-only overlay (then reboot)
#   sudo bash scripts/overlay.sh off      # writable for updates (then reboot)
#   bash scripts/overlay.sh on --dry-run  # print what it would do, change nothing
#
# Wraps raspi-config's non-interactive overlayfs functions. A reboot is required
# for any change to take effect (raspi-config rewrites the boot config + initramfs).

set -euo pipefail

CMD="${1:-status}"
DRY=0
[[ "${2:-}" == "--dry-run" ]] && DRY=1

run() {
  if [[ "$DRY" == "1" ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

case "$CMD" in
  status)
    if [[ "$DRY" == "1" ]]; then
      echo "[dry-run] raspi-config nonint get_overlay_now"
      exit 0
    fi
    # get_overlay_now exits 0 when the overlay is currently active.
    if raspi-config nonint get_overlay_now 2>/dev/null; then
      echo "overlay: ON (SD read-only — safe to unplug)"
    else
      echo "overlay: OFF (SD writable — do NOT pull power mid-write; turn ON before shipping)"
    fi
    ;;
  on)
    run sudo raspi-config nonint enable_overlayfs
    echo "Overlay ENABLED. Reboot to apply:  sudo reboot"
    echo "After reboot the SD is read-only and the unit is safe to unplug at any time."
    ;;
  off)
    run sudo raspi-config nonint disable_overlayfs
    echo "Overlay DISABLED. Reboot to apply:  sudo reboot"
    echo "The SD is now writable for updates (apt/git/etc.). Re-enable with 'on' + reboot when done."
    ;;
  *)
    echo "usage: overlay.sh {status|on|off} [--dry-run]" >&2
    exit 2
    ;;
esac
