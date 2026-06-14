#!/usr/bin/env bash
# setup-ap.sh up|down — bring the SETUP-mode open AP up/down via NetworkManager.
# Open AP (no password) in shared mode: NM provides DHCP + gateway 10.42.0.1, so
# a phone that connects gets an IP and can reach the captive portal. ⚠️ Hardware:
# the SSID/band/iface may need tuning on the Pi.
set -euo pipefail

IFACE="${SETUP_AP_IFACE:-wlan0}"
CON="sunset-setup-ap"

mac_suffix() {
  # last 4 hex of the wlan0 MAC, uppercased, colons stripped
  tr -d ':' < "/sys/class/net/${IFACE}/address" | tail -c 5 | tr 'a-f' 'A-F'
}

up() {
  local ssid="Sunset-Cam-$(mac_suffix)"
  # Remove any stale profile, then create an OPEN AP in shared mode.
  nmcli connection delete "$CON" >/dev/null 2>&1 || true
  nmcli connection add type wifi ifname "$IFACE" con-name "$CON" autoconnect no ssid "$ssid"
  nmcli connection modify "$CON" \
    802-11-wireless.mode ap 802-11-wireless.band bg \
    ipv4.method shared
  nmcli connection up "$CON"
  echo "[setup-ap] up: SSID=$ssid (open, shared, gateway 10.42.0.1)"
}

down() {
  nmcli connection down "$CON" >/dev/null 2>&1 || true
  nmcli connection delete "$CON" >/dev/null 2>&1 || true
  echo "[setup-ap] down"
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  *) echo "usage: $0 up|down" >&2; exit 2 ;;
esac
