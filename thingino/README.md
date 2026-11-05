# Thingino cameras: `sunset-agent`

A shell agent that turns a camera running [Thingino](https://github.com/themactep/thingino-firmware)
open firmware (Wyze v2/v3, Sonoff CAM-S2/B1P, Tapo, Vanhua T31 boards…) into a
Sunrise/Sunset network camera. It is the thin-client counterpart of the Pi
firmware in `src/sunset_cam/` and speaks the same wire protocol
(`the-sunset-webcam-map/docs/device-protocol.md`).

None of the Pi code can run on these cameras (MIPS SoC, 8–16 MB flash, busybox,
no Python), so the agent uses only what stock Thingino ships with: POSIX sh,
busybox awk, `curl`, `jct` (Thingino's JSON tool) and `prudyntctl` (its
streamer control, which writes a JPEG snapshot to stdout).

| | Pi firmware | `sunset-agent` |
|---|---|---|
| Onboarding | provision → register → heartbeat | same (register only if `CLAIM_CODE` is set) |
| Aim | MPU6050 gyro reports azimuth/tilt | typed into config, reported once to `/placement` |
| Capture window | hardcoded UTC times in config (Tier 0) | computed on the camera daily (NOAA almanac, within ~2 min of `astral`) |
| Cadence | 1 fps | `INTERVAL_S`, default 20 s |
| Directives (`wipe_wifi`, logs) | executed | ignored for now |

Files:

- `sunset-agent`: the agent (`run`, `windows`, `snap`, `heartbeat`).
- `S99sunset-agent`: init script.
- `sunset-agent.conf.example`: config template.
- Tests: `tests/test_thingino_agent.py` runs the real script under `dash` against a
  mock of the app's endpoints, and checks the sun math against `astral`. It needs
  `dash` and `jct` on PATH (`git clone https://github.com/themactep/jct && make`),
  otherwise it skips.

## First-camera test plan

Goal: one Thingino camera uploads a full sunset window into production, survives
a reboot, and its frames get scored like any Pi frame.

### 0. Pick the camera
A **Wyze Cam v3** or **Sonoff CAM-S2**: both install Thingino from an SD card,
no case opening. (The Sonoff B1P is the bulk candidate, but its SD install
isn't confirmed yet, so test it second.) Note the exact model and board
revision; `ipctool` from OpenIPC will tell you.

### 1. Flash and check the basics
1. Flash Thingino with its SD-card installer and finish its setup (Wi-Fi, root
   password). Enable SSH in the web UI if it isn't on.
2. SSH in (`ssh root@<camera-ip>`) and check:
   ```sh
   date -u                                  # correct UTC time? (ntpd)
   prudyntctl snapshot -c 0 > /tmp/t.jpg; ls -l /tmp/t.jpg   # a JPEG of ~100–400 KB
   curl -sS -o /dev/null -w '%{http_code}\n' https://sunrisesunset.studio   # 200, i.e. TLS works
   which jct awk logger soc                 # all present
   soc -s                                   # SoC serial, used for the hardware id
   ```
   If `prudyntctl` is missing on your build, set `SNAPSHOT_CMD` in the config to
   any command that prints a JPEG to stdout.

### 2. Create the camera in the app
Two ways. **B is the real flow**; A is a quicker bench test.

**A. Tier0 (quick, aim typed by hand).** From the parent repo (writes to production):
```sh
DATABASE_URL=... ./scripts/tier0-create-camera.sh \
  --hardware-id thingino-<soc -s output> \
  --lat 48.75 --lng -122.48 --timezone America/Los_Angeles \
  --title "Thingino test 1" --phase sunset
```
It prints `camera_id` and `device_token` (shown once). Put them in the config
with `LAT`, `LNG` and `AZIMUTH_DEG`.

**B. Claim code + phone setup (aim from the phone, printed mount).**
```sh
curl -sS -X POST https://sunrisesunset.studio/api/cameras/provision \
  -H "Authorization: Bearer $CRON_SECRET" -H 'Content-Type: application/json' \
  -d '{"hardware_id":"thingino-<soc -s output>","device_class":"thingino-wyze-v3","label":"wyze-1"}'
```
It returns `camera_id`, `claim_code` and `device_token` (shown once). Put all
three in the config, with `HARDWARE_ID` exactly as provisioned and
`CAMERA_MODEL="wyze-v3"`. Leave `AZIMUTH_DEG` empty. Then open
`https://sunrisesunset.studio/setup/<claim_code>` on your phone. The app knows
the camera model, so it uses this camera's field of view, measures your window,
and tells you which wedge to print: `hardware/window-wedge-mount.scad` with
`wedge_deg`, `tall_end` and `camera` filled in. Once you submit, the camera's
next heartbeat says `ready` and capture starts on its own.

### 3. Install the agent
From this repo (dropbear may not have `scp`, so pipe through `ssh`):
```sh
CAM=root@<camera-ip>
ssh $CAM 'cat > /usr/sbin/sunset-agent && chmod +x /usr/sbin/sunset-agent' < thingino/sunset-agent
ssh $CAM 'cat > /etc/init.d/S99sunset-agent && chmod +x /etc/init.d/S99sunset-agent' < thingino/S99sunset-agent
cp thingino/sunset-agent.conf.example /tmp/sa.conf   # fill in CAMERA_ID, DEVICE_TOKEN, LAT, LNG, AZIMUTH_DEG
ssh $CAM 'cat > /etc/sunset-agent.conf && chmod 600 /etc/sunset-agent.conf' < /tmp/sa.conf
```
Thingino's root filesystem is a writable overlay, so these survive reboots
(but not a full reflash).

### 4. Bench checks (camera on your desk)
```sh
sunset-agent heartbeat   # 200 + placement_status; the tier0 camera says awaiting_aim until aim is sent
sunset-agent snap        # "uploaded manual-… (N bytes)"; the frame shows up on /cameras/<id>
sunset-agent windows     # tonight's window, e.g. sunset start=…T00:00Z event=…T00:45Z
```
Check the `windows` event time against a sunset table for your location.

### 5. Mount it and run
Mount it facing the sunset with a clear horizon (no windows, no sidewalks in
frame): in the printed window mount (path B), or anywhere with `AZIMUTH_DEG`
set from a phone compass (path A). Then:
```sh
/etc/init.d/S99sunset-agent start
logread -f | grep sunset-agent
```
You should see `reported aim … HTTP 200`, then at window start `window open:`
followed by an `uploaded …` line every ~20 s.

### 6. Pass criteria
- [ ] One full window uploaded: about 75 min / 20 s ≈ 225 frames, all sharing one `window_id`, with `frame_seq` counting up.
- [ ] Frames appear on the camera page and get model scores like Pi frames.
- [ ] Reboot the camera: the agent starts by itself and the next window uploads too.
- [ ] Pull the network mid-window: the agent logs failures, doesn't crash, and resumes.
- [ ] Note bandwidth: ~225 × frame size per window (≈45 MB at 200 KB).

### Troubleshooting
| Log line | Meaning |
|---|---|
| `heartbeat failed: HTTP 000` | No network or TLS failure; rerun the `curl` check in step 1. |
| `HTTP 401` / `token rejected` | Wrong `CAMERA_ID`/`DEVICE_TOKEN` pair, or the camera was revoked. |
| `HTTP 404: camera has no paired webcam row` | The camera was made without the tier0 seed or a deployment. |
| `server is awaiting aim` | Set `AZIMUTH_DEG` and `TILT_DEG`. |
| Nothing uploads, no `window open` | Check `date -u`; run `sunset-agent windows`. |
| Dark or black frames | Night mode/IR cut kicked in at dusk. Turn off Thingino's automatic day/night switching (or its sunset-based dusk2dawn) for this camera. |

## Known gaps
- **Aim** comes from the phone app (path B), or is typed by hand (path A). Cameras on their own swivel stand, rather than a window mount, still need a phone-aim step in the app (issue #499 in the app repo).
- **Windows** are computed on the camera. The plan is for the server to send the next window in the heartbeat reply; the agent will prefer that when present (issue in the app repo).
- **`window_id`** uses the UTC date of the sun event, so a Pacific evening sunset carries the next day's date.
- **Packaging**: for more than a few cameras, bake the agent and init script into a custom Thingino image (`user/common/overlay/` in the Thingino build) and read the config from the SD card.
- Directives (`wipe_wifi`, log shipping) and remote updates (`sysupgrade`) aren't handled yet.
