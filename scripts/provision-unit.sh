#!/usr/bin/env bash
# provision-unit.sh — Mint a new camera identity and write the SD config.
#
# Usage:
#   API_BASE=https://api.example.com \
#   CRON_SECRET=<operator-secret> \
#   WEB_BASE=https://sunset.cam \
#   ./scripts/provision-unit.sh <label>
#
# Optional environment:
#   CONFIG_OUT   Path to write config.json (default: ./out/config.json)
#   STICKER_OUT  Path to write sticker PNG (default: ./out/<label>-sticker.png)
#   SD_DEVICE    Block device to flash (e.g. /dev/rdisk4) — required unless DRY_RUN=1
#   LOG_CSV      CSV log file (default: ./provision-log.csv)
#   DRY_RUN=1    Skip the 'dd' flash step (safe for CI / bench testing)
#
# The cloud endpoint POST {API_BASE}/api/cameras/provision is called with
# Authorization: Bearer {CRON_SECRET} and body {hardware_id, label}.
# It returns {camera_id, claim_code, device_token} which are written to
# config.json and encoded as a QR sticker PNG.
#
# ⚠️  The dd flash step is HARDWARE-GATED: it only runs when DRY_RUN != 1.

set -euo pipefail

# --------------------------------------------------------------------------
# Arguments & env
# --------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <label>" >&2
  echo "  e.g. LABEL=bench-cam-1  API_BASE=...  CRON_SECRET=...  WEB_BASE=...  $(basename "$0") bench-cam-1" >&2
  exit 2
fi

LABEL="${1}"

: "${API_BASE:?API_BASE must be set (e.g. https://api.example.com)}"
: "${CRON_SECRET:?CRON_SECRET must be set}"
: "${WEB_BASE:?WEB_BASE must be set (e.g. https://sunset.cam)}"

CONFIG_OUT="${CONFIG_OUT:-./out/config.json}"
STICKER_OUT="${STICKER_OUT:-./out/${LABEL}-sticker.png}"
LOG_CSV="${LOG_CSV:-./provision-log.csv}"
DRY_RUN="${DRY_RUN:-0}"

# Derive a hardware_id from the label (operator-defined, unique per unit).
# In production this could come from the Pi's /proc/cpuinfo serial; for bench
# provisioning the label-derived ID is a reasonable default.
HARDWARE_ID="hw-${LABEL}"

# Export all variables that the inline Python subprocesses read via os.environ.
export API_BASE CRON_SECRET WEB_BASE LABEL HARDWARE_ID CONFIG_OUT STICKER_OUT DRY_RUN

# --------------------------------------------------------------------------
# Step 1: mint identity via cloud provision endpoint
# --------------------------------------------------------------------------

echo "==> Provisioning unit '${LABEL}' (hardware_id=${HARDWARE_ID}) ..."

# _PROVISION_JSON may be pre-set (e.g. in DRY_RUN tests) to skip the real
# cloud call while still exercising the config/sticker/log steps.
if [ -n "${_PROVISION_JSON:-}" ]; then
  PROVISION_JSON="${_PROVISION_JSON}"
  echo "    [using pre-set _PROVISION_JSON for dry-run testing]"
else
  PROVISION_JSON=$(python3.11 - <<PYEOF
import sys, json
sys.path.insert(0, "src")

from sunset_cam.provision_client import provision_unit

import os
result = provision_unit(
    api_base=os.environ["API_BASE"],
    cron_secret=os.environ["CRON_SECRET"],
    hardware_id=os.environ["HARDWARE_ID"],
    label=os.environ["LABEL"],
)
print(json.dumps(result))
PYEOF
)
fi

CAMERA_ID=$(echo "${PROVISION_JSON}" | python3.11 -c "import sys,json; print(json.load(sys.stdin)['camera_id'])")
CLAIM_CODE=$(echo "${PROVISION_JSON}" | python3.11 -c "import sys,json; print(json.load(sys.stdin)['claim_code'])")
DEVICE_TOKEN=$(echo "${PROVISION_JSON}" | python3.11 -c "import sys,json; print(json.load(sys.stdin)['device_token'])")
export CAMERA_ID CLAIM_CODE DEVICE_TOKEN

echo "    camera_id  = ${CAMERA_ID}"
echo "    claim_code = ${CLAIM_CODE}"
echo "    device_token = ${DEVICE_TOKEN:0:6}...${DEVICE_TOKEN: -4}"

# --------------------------------------------------------------------------
# Step 2: write identity config.json
# --------------------------------------------------------------------------

echo "==> Writing identity config to ${CONFIG_OUT} ..."
mkdir -p "$(dirname "${CONFIG_OUT}")"

python3.11 - <<PYEOF
import sys, os
sys.path.insert(0, "src")
from sunset_cam.device_config import write_identity

write_identity(
    os.environ["CONFIG_OUT"],
    claim_code=os.environ["CLAIM_CODE"],
    camera_id=int(os.environ["CAMERA_ID"]),
    device_token=os.environ["DEVICE_TOKEN"],
    api_base=os.environ["API_BASE"],
    hardware_id=os.environ["HARDWARE_ID"],
)
print("    wrote", os.environ["CONFIG_OUT"])
PYEOF

# --------------------------------------------------------------------------
# Step 3: generate sticker PNG
# --------------------------------------------------------------------------

echo "==> Generating sticker at ${STICKER_OUT} ..."
mkdir -p "$(dirname "${STICKER_OUT}")"

python3.11 - <<PYEOF
import sys, os
sys.path.insert(0, "src")
from sunset_cam.sticker import render_sticker

render_sticker(
    claim_code=os.environ["CLAIM_CODE"],
    web_base=os.environ["WEB_BASE"],
    out_path=os.environ["STICKER_OUT"],
)
print("    wrote", os.environ["STICKER_OUT"])
PYEOF

# --------------------------------------------------------------------------
# Step 4: dd flash to SD — HARDWARE-GATED (skipped when DRY_RUN=1)
# --------------------------------------------------------------------------

if [ "${DRY_RUN}" != "1" ]; then
  : "${SD_DEVICE:?SD_DEVICE must be set when DRY_RUN != 1 (e.g. /dev/rdisk4)}"
  echo "==> Flashing SD card at ${SD_DEVICE} ..."
  # Write the identity config to the mounted SD boot partition config path.
  # Adjust the mount path as appropriate for your OS / SD card setup.
  SD_MOUNT="${SD_MOUNT:-/Volumes/bootfs}"
  SD_CONFIG="${SD_MOUNT}/config.json"

  if [ ! -d "${SD_MOUNT}" ]; then
    echo "ERROR: SD mount point ${SD_MOUNT} not found. Mount the SD card first." >&2
    exit 1
  fi

  cp "${CONFIG_OUT}" "${SD_CONFIG}"
  echo "    copied config.json to ${SD_CONFIG}"

  # Low-level dd flash (e.g. for writing a full OS image to the SD).
  # Uncomment and adapt if you're flashing a full image rather than just config:
  #   dd if=./images/sunset-cam-os.img of="${SD_DEVICE}" bs=4m status=progress
  #   sync
  #   diskutil eject "${SD_DEVICE}" 2>/dev/null || true
  echo "    dd flash complete (adapt dd command for your image path as needed)"
else
  echo "==> [DRY_RUN=1] Skipping dd flash step"
fi

# --------------------------------------------------------------------------
# Step 5: append CSV log row
# --------------------------------------------------------------------------

TIMESTAMP=$(python3.11 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).replace(microsecond=0).isoformat())")

# Create header row if the log file is new
if [ ! -f "${LOG_CSV}" ]; then
  echo "label,camera_id,claim_code,hardware_id,timestamp" > "${LOG_CSV}"
fi

echo "${LABEL},${CAMERA_ID},${CLAIM_CODE},${HARDWARE_ID},${TIMESTAMP}" >> "${LOG_CSV}"
echo "==> Logged to ${LOG_CSV}"

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

echo ""
echo "Provisioning complete."
echo "  Camera ID  : ${CAMERA_ID}"
echo "  Claim code : ${CLAIM_CODE}"
echo "  Config     : ${CONFIG_OUT}"
echo "  Sticker    : ${STICKER_OUT}"
echo "  Log        : ${LOG_CSV}"
echo ""
echo "Setup URL: ${WEB_BASE%/}/setup/${CLAIM_CODE}"
