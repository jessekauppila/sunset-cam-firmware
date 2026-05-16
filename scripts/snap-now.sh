#!/usr/bin/env bash
# "What does the camera see right now?" — on-demand verification helper.
#
# Captures a single frame on the Pi via `rpicam-still`, scps it back to the
# caller's machine, and prints pixel-brightness stats so you can tell at a
# glance whether the camera is healthy or pointed at a wall.
#
# Bypasses the firmware's capture window AND the upload pipeline — no DB
# rows, no Firebase writes, no snapshot history pollution. Pure diagnostic.
#
# Bridge artifact toward the "First-image verification" step in the
# streamlined-deployment decomposition (see parent repo's
# docs/superpowers/specs/2026-05-15-streamlined-deployment-overview.md).
#
# Usage from the dev machine:
#   scripts/snap-now.sh                          # auto-exposure, defaults
#   scripts/snap-now.sh --host pi@cam-2.local    # different device
#   scripts/snap-now.sh --long                   # 2s exposure + gain 16
#                                                # (use when the scene is dark
#                                                # to verify the camera is
#                                                # functional, not just dim)
#   scripts/snap-now.sh --out ~/my-frame.jpg
#
# Requires: ssh access to the Pi, rpicam-still installed there (default on
# Bookworm), Python 3 with PIL on the local machine for the stats summary.

set -euo pipefail

HOST="pi@sunset-cam-0.local"
LOCAL_OUT="/tmp/snap-now.jpg"
LONG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --out)  LOCAL_OUT="$2"; shift 2 ;;
    --long) LONG=1; shift ;;
    -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

REMOTE_OUT="/tmp/snap-now.jpg"

if [[ "$LONG" == "1" ]]; then
  # 2s exposure, high analog gain, denoise off. Surfaces any structure even
  # at midnight; useful as the "is the lens covered?" check.
  CAPTURE='rpicam-still --immediate -n --width 1920 --height 1080 \
    --shutter 2000000 --gain 16 --denoise off --awb auto -o '"$REMOTE_OUT"
else
  CAPTURE='rpicam-still --immediate -n --width 1920 --height 1080 \
    -t 100 -o '"$REMOTE_OUT"
fi

echo "snapping on $HOST (long=$LONG)..."
ssh -o ConnectTimeout=10 "$HOST" "rm -f $REMOTE_OUT && $CAPTURE 2>&1 | tail -3"
scp -o ConnectTimeout=10 "$HOST:$REMOTE_OUT" "$LOCAL_OUT" >/dev/null
echo "saved: $LOCAL_OUT"

python3 - "$LOCAL_OUT" <<'PYEOF'
import sys
from PIL import Image, ImageStat
import numpy as np

p = sys.argv[1]
im = Image.open(p).convert("RGB")
stat = ImageStat.Stat(im)
arr = np.array(im)
total = arr.shape[0] * arr.shape[1]
mean = sum(stat.mean) / 3

print(f"size:       {im.size[0]}x{im.size[1]}")
print(f"mean RGB:   {[round(v,2) for v in stat.mean]}")
print(f"stddev:     {[round(v,2) for v in stat.stddev]}")
print(f"brightness: {round(mean,2)} / 255  ({round(mean*100/255,1)}%)")
buckets = []
for t in (5, 16, 32, 64, 128, 192):
    pct = 100 * (arr.max(axis=2) > t).sum() / total
    buckets.append(f">{t}: {pct:5.2f}%")
print("structure:  " + "  ".join(buckets))

# Heuristic verdict — the user asked "is the camera healthy" and this is the
# answer worth printing. Tuned against an actual midnight scene from a Pi
# Camera Module 2 (imx219) on 2026-05-15: long-exposure mean ~41/255 with
# clearly visible structure (streetlamp, treetops); short-exposure mean ~2.6
# with only hot-pixel signal.
if mean < 1.0 and arr.max() < 20:
    print("verdict:    ⚠ uniformly dark — lens may be covered, sensor failed, "
          "or the scene is genuinely lightless")
elif mean < 5.0:
    print("verdict:    scene is dark; if --long shows structure the camera is healthy")
else:
    print("verdict:    ✓ camera sees a real scene")
PYEOF
