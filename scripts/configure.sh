#!/usr/bin/env bash
# Write /opt/sunset-cam/config/config.json without editing JSON by hand,
# then restart the systemd unit so the new window takes effect.
#
# Typical day-to-day use (just refresh the window for tonight's sunset):
#   bash scripts/configure.sh \
#     --window-id 2026-05-16-sunset-cam1 \
#     --window-start 2026-05-17T03:00:00Z \
#     --window-end   2026-05-17T04:30:00Z
#
# Quick test (capture window starts now, runs N minutes):
#   bash scripts/configure.sh \
#     --window-id quick-test \
#     --window-from-now-min 0 --window-duration-min 30
#
# Initial setup (only needed once per device after running install.sh):
#   bash scripts/configure.sh \
#     --camera-id 1 --device-token "<64 hex>" \
#     --phase sunset --api-base https://www.sunrisesunset.studio \
#     --window-id setup --window-from-now-min 0 --window-duration-min 30
#
# Other flags:
#   --log-level INFO|DEBUG     (default keeps current; INFO on first write)
#   --capture-interval-s 1.0   (default keeps current; 1.0 on first write)
#   --no-restart               (just write the file)
#   --config <path>            (default /opt/sunset-cam/config/config.json)
#   --dry-run                  (print the new config, don't write)

set -euo pipefail

CONFIG_PATH="/opt/sunset-cam/config/config.json"
SERVICE="sunset-cam.service"

CAMERA_ID=""
DEVICE_TOKEN=""
API_BASE=""
PHASE=""
WINDOW_ID=""
WINDOW_START=""
WINDOW_END=""
FROM_NOW_MIN=""
DURATION_MIN=""
LOG_LEVEL=""
CAPTURE_INTERVAL_S=""
RESTART=1
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --camera-id)            CAMERA_ID="$2"; shift 2 ;;
    --device-token)         DEVICE_TOKEN="$2"; shift 2 ;;
    --api-base)             API_BASE="$2"; shift 2 ;;
    --phase)                PHASE="$2"; shift 2 ;;
    --window-id)            WINDOW_ID="$2"; shift 2 ;;
    --window-start)         WINDOW_START="$2"; shift 2 ;;
    --window-end)           WINDOW_END="$2"; shift 2 ;;
    --window-from-now-min)  FROM_NOW_MIN="$2"; shift 2 ;;
    --window-duration-min)  DURATION_MIN="$2"; shift 2 ;;
    --log-level)            LOG_LEVEL="$2"; shift 2 ;;
    --capture-interval-s)   CAPTURE_INTERVAL_S="$2"; shift 2 ;;
    --config)               CONFIG_PATH="$2"; shift 2 ;;
    --no-restart)           RESTART=0; shift ;;
    --dry-run)              DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,29p' "$0"
      exit 0
      ;;
    *)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
  esac
done

# All JSON math + UTC datetime math happens in python — bash arithmetic and
# `date` flag differences (BSD vs GNU) are too error-prone, especially over
# SSH with terminal-paste mangling. Pass values via env to keep quoting sane.
export CONFIG_PATH CAMERA_ID DEVICE_TOKEN API_BASE PHASE WINDOW_ID \
       WINDOW_START WINDOW_END FROM_NOW_MIN DURATION_MIN \
       LOG_LEVEL CAPTURE_INTERVAL_S DRY_RUN

python3 - <<'PYEOF'
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

def env(name, cast=None):
    v = os.environ.get(name, "")
    if v == "":
        return None
    return cast(v) if cast else v

path = Path(os.environ["CONFIG_PATH"])
cfg = {}
if path.exists():
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"existing config is not valid JSON ({path}): {e}")

def set_if(key, value):
    if value is not None:
        cfg[key] = value

set_if("camera_id",    env("CAMERA_ID", int))
set_if("device_token", env("DEVICE_TOKEN"))
set_if("api_base",     env("API_BASE"))
set_if("phase",        env("PHASE"))
set_if("window_id",    env("WINDOW_ID"))

start = env("WINDOW_START")
end   = env("WINDOW_END")
from_now = env("FROM_NOW_MIN", int)
duration = env("DURATION_MIN", int)

if (start or end) and (from_now is not None or duration is not None):
    sys.exit("pass either --window-start/--window-end OR --window-from-now-min/"
             "--window-duration-min, not both")

if from_now is not None or duration is not None:
    if duration is None:
        sys.exit("--window-duration-min is required with --window-from-now-min")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    s = now + timedelta(minutes=from_now or 0)
    e = s + timedelta(minutes=duration)
    iso = lambda d: d.isoformat().replace("+00:00", "Z")
    cfg["capture_window_start_utc"] = iso(s)
    cfg["capture_window_end_utc"]   = iso(e)
else:
    set_if("capture_window_start_utc", start)
    set_if("capture_window_end_utc",   end)

set_if("log_level",          env("LOG_LEVEL"))
set_if("capture_interval_s", env("CAPTURE_INTERVAL_S", float))

# First-write defaults so a fresh install doesn't crash load_config().
cfg.setdefault("api_base", "https://www.sunrisesunset.studio")
cfg.setdefault("phase", "sunset")
cfg.setdefault("capture_interval_s", 1.0)
cfg.setdefault("log_level", "INFO")

required = ("camera_id", "device_token", "api_base", "phase", "window_id",
            "capture_window_start_utc", "capture_window_end_utc",
            "capture_interval_s")
missing = [k for k in required if k not in cfg or cfg[k] in (None, "")]
if missing:
    sys.exit(f"config still missing required keys after merge: {missing}. "
             f"Pass them as flags (e.g. --camera-id ... --device-token ...).")

# Sanity: window must parse as ISO8601 and end must be after start.
def parse(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00"))
try:
    s = parse(cfg["capture_window_start_utc"])
    e = parse(cfg["capture_window_end_utc"])
except ValueError as ex:
    sys.exit(f"window timestamps must be ISO8601: {ex}")
if e <= s:
    sys.exit(f"window end ({cfg['capture_window_end_utc']}) is not after "
             f"start ({cfg['capture_window_start_utc']})")

text = json.dumps(cfg, indent=2) + "\n"

if os.environ.get("DRY_RUN") == "1":
    print("=== DRY RUN ===")
    print(f"would write to: {path}")
    print(text, end="")
    sys.exit(0)

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(text)

# Redact the token before printing back so journals/copy-paste don't leak it.
redacted = {**cfg, "device_token": cfg["device_token"][:6] + "..." + cfg["device_token"][-4:]}
print("wrote", path)
print(json.dumps(redacted, indent=2))
PYEOF

if [[ "$DRY_RUN" == "1" || "$RESTART" == "0" ]]; then
  exit 0
fi

# Restart the unit so it reloads config.json. Try sudo first (works if NOPASSWD
# is set up for systemctl); fall back to SIGKILL on the firmware process and
# rely on the unit's `Restart=on-failure` to bring it back. The fallback exists
# because most Pi installs don't bother with NOPASSWD just for one service.
echo "restarting $SERVICE..."
if sudo -n systemctl restart "$SERVICE" 2>/dev/null; then
  echo "  via sudo systemctl"
else
  pid="$(pgrep -f 'sunset_cam.main' | head -1 || true)"
  if [[ -z "$pid" ]]; then
    echo "  process not running; sudo password required to start it:" >&2
    echo "    sudo systemctl start $SERVICE" >&2
    exit 1
  fi
  kill -9 "$pid"
  echo "  killed PID $pid; systemd will auto-restart in ~5s (Restart=on-failure)"
  sleep 6
fi

systemctl status "$SERVICE" --no-pager -l 2>/dev/null | head -5 || true
echo
echo "tail logs with: journalctl -u $SERVICE -f"
