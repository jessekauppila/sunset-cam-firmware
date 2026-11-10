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
- `new-camera`: one command per camera: creates it on the server and makes its setup card.
- `prepare-sd`: writes SD cards (Thingino installer, setup card, revert card). macOS.
- `card-install.sh`: what a setup card runs on the camera to install the agent.
- `sunset-agent.conf.example`: config template.
- Tests: `tests/test_thingino_agent.py` runs the real script under `dash` against a
  mock of the app's endpoints, and checks the sun math against `astral`. It needs
  `dash` and `jct` on PATH (`git clone https://github.com/themactep/jct && make`),
  otherwise it skips.

## Setup card: one command per camera

```sh
CRON_SECRET=... thingino/new-camera --label wyze-2 --wifi-ssid "Home-2.4" wyze-cam-3
```
This creates the camera on the server (**it writes to production**), saves its
config under `~/.sunset-cam/cameras/<id>-wyze-2/`, and writes one SD card that

- flashes the **current** Thingino release (not the months-old build inside
  the installer, so there is no `sysupgrade -f` and no second Wi-Fi setup),
- installs the agent and this camera's config,
- carries the Wi-Fi (asked for once, on the Mac; a `-5G` name is refused, the
  cameras are 2.4 GHz only),
- sets a random root password, saved beside the config as `rootpass.txt`.

It prints the claim code and the setup URL: print that URL as a QR code on the
camera's sticker.

Then, for whoever sets the camera up:
1. Put the card in the camera and power it on. Wait for the light to stop
   cycling red/blue (about four minutes).
2. Scan the sticker and follow the phone setup.

Without `--wifi-ssid` there is one more step between those: join the camera's
`THINGINO-XXXX` Wi-Fi (password `thingino`) from a phone and give it the home
network and a root password.

No SSH, nothing typed into a config file. Variations:

- **Already running Thingino** (or no installer for the model, like the Pan
  v3): `thingino/new-camera --fat32 --camera-model wyze-v3`. The card then
  carries only the agent and config.
- **The card failed to write**: `thingino/new-camera --from <the saved folder> wyze-cam-3`
  retries without creating a second camera (and keeps its root password).
- **Agent update for a camera in the field**: `thingino/prepare-sd --fat32 --stage-agent`.
  The camera keeps its own config.
- **Offline, or the release won't download**: `prepare-sd --bundled-thingino`
  writes the installer as it comes. Expect the upgrade and the second Wi-Fi
  setup described in the test plan below.

### How it works

**Current Thingino.** A thingino-installers card is plain files on FAT32: a
boot file plus one 16 MB `thingino-<board>.bin` per hardware variant, which
the installer's own build script downloads from Thingino's latest release.
`prepare-sd` writes and verifies the installer image, then replaces each
`thingino-*.bin` with today's release of the same name. Each download is
checked against the `.sha256sum` Thingino publishes with it and must be the
same size as the file it replaces; if any of that fails, the script stops
before the card is touched.

**Self-install.** Thingino runs `runonce.sh` from the card's root each time the
card mounts, until it exits 0 (`/lib/mdev/automount`). Ours calls
`sunset/install.sh` (`card-install.sh` in this repo), which copies the agent
into place, sets the root password and starts the agent. The card's secrets
(the config with the device token, the root password, the Wi-Fi password in
`uenv.txt`) are deleted from the card only at the *next* boot, once the
installed copy has survived a restart. That matters because the card's
installer boots from the same card first, and a copy made there would be lost.

**File names on the card.** On the camera, opening a name on the card can
return a *different file whose name is the start of it*. With `sunset-agent`
on the card, `sunset-agent.conf` opened `sunset-agent`, whether or not a real
`sunset-agent.conf` was there, and the first Cam v3 installed the agent script
as its own config. The Mac reads the same card correctly, so nothing shows up
until the camera runs. Hence the card's own names, none of which begins
another:

| On the card (`sunset/`) | Becomes, on the camera |
|---|---|
| `agent.sh` | `/usr/sbin/sunset-agent` |
| `initd.sh` | `/etc/init.d/S99sunset-agent` |
| `findled.sh` | `/usr/sbin/find-status-led` |
| `camera.conf` | `/etc/sunset-agent.conf` |
| `example.conf` | the same, as a template, when the card has no config |
| `rootpass.txt` | root's password |
| `install.sh`, `stamp.txt` | (the installer and its note of which boot it ran in) |

Rules for anything that runs on the camera and touches the card: never give
two files names where one starts the other; test for a file with the folder's
listing, not `[ -f ]`; don't create work files on the card. And Thingino's
busybox is small (no `cmp`, for one): `tests/test_card_install.py` runs the
script with only the commands seen on a Cam v3.

### What has been tried, and what hasn't

Tried on camera 3 (Cam v3, Thingino 2026-11-05):
- `runonce.sh` is run at mount by this build, and `runonce.done` stops it.
- `install.sh`, run on the camera against a scratch copy of the card's layout
  on its own SD card and a temporary root: first boot installs and starts,
  the same boot again changes nothing, the next boot removes the config, the
  root password and the Wi-Fi lines and exits 0. (This is where the missing
  `cmp` and the file-name problem were found.)
- The release swap, against the real `wyze-cam-3` installer image and the real
  release with a stand-in for the card: all three builds downloaded, checked
  and replaced. The `t31x_gc2053_atbm6031` build it put on the card is
  byte-for-byte the one camera 3 is running.

Not tried, because it needs a camera that still runs Wyze firmware:
- A whole flash from a card with the swapped builds. The reasoning is that the
  card is then exactly what the installer's build script would produce today,
  but no camera has been flashed from one yet. Keep the first one on the bench
  with the Mac nearby, and use `--bundled-thingino` if it misbehaves.
- Whether a freshly flashed camera reads the Wi-Fi from `uenv.txt` on its very
  first boot. After the `sysupgrade` on camera 3 it took a second boot (the
  first came up in the setup hotspot). If that happens, unplug and replug.
- Whether the installer itself runs `runonce.sh` while flashing. The two-boot
  rule is there so that this is harmless either way.
- Setting the root password for real: on the camera the script ran with a
  stand-in for `chpasswd`. It makes the same call Thingino's setup page makes
  (`chpasswd -c sha512`), and says so loudly if it fails. Until one camera
  proves it, check `ssh root@<camera>` refuses `root` as the password.

## First-camera test plan

Goal: one Thingino camera uploads a full sunset window into production, survives
a reboot, and its frames get scored like any Pi frame.

### 0. Pick the camera
A **Wyze Cam v3** or **Sonoff CAM-S2**: both install Thingino from an SD card,
no case opening. (The Sonoff B1P is the bulk candidate; it has an SD installer
now, but a failed flash needs a flash programmer to recover, so test it
second.) The Wyze v3 installer picks the board variant itself; note which
image it chose after first boot (`/etc/os-release`).

> **Not the Wyze Cam _Pan_ v3.** Despite the name it's a different path: there is
> no SD installer for it, and its stock SD recovery is reported broken on this
> model, so no restore path can be proven before writing. Do not flash it yet —
> see `docs/thingino-pan-v3-flash-handoff.md` for the verdict and what has to
> land first.

### 1. Flash and check the basics
1. Write the installer to an SD card with `thingino/prepare-sd wyze-cam-3`
   (macOS; `--list` first to see which disks it will accept; `--stage-agent`
   also puts the agent on the card). Then flash and finish setup (Wi-Fi, root
   password). Enable SSH in the web UI if it isn't on.
   - **Save the backup.** The installer writes this camera's stock firmware to
     `WYZE_BACKUP_*/combined_backup.bin` on the card. Copy it off; it is the
     only way back to Wyze for this unit. Make the revert card with
     `thingino/prepare-sd --revert combined_backup.bin`.
   - The installer's bundled Thingino builds are old (installers issue #73).
     `prepare-sd` replaces them with the current release as it writes the
     card; with `--bundled-thingino`, expect to `sysupgrade -f` and set up
     Wi-Fi a second time.
   - Known failure (installers issue #72, one early-revision unit): a
     red/blue/purple LED cycle for about a minute, then solid red, repeating.
     If you see that, stop and read the issue before trying more cards.
   - `prepare-sd --fat32 --copy FILE[:NAME]` erases a card as FAT32 and copies
     named files to its root, for any "put a file on the card" path.
2. SSH in (`ssh root@<camera-ip>`) and check:
   ```sh
   date -u                                  # correct UTC time? (ntpd)
   prudyntctl snapshot -c 0 > /tmp/t.jpg; ls -l /tmp/t.jpg   # a JPEG of ~100–400 KB
   curl -sS -o /dev/null -w '%{http_code}\n' https://www.sunrisesunset.studio   # 200, i.e. TLS works
   which jct awk logger soc                 # all present
   soc -s                                   # SoC serial, used for the hardware id
   ```
   If `prudyntctl` is missing on your build, set `SNAPSHOT_CMD` in the config to
   any command that prints a JPEG to stdout.

### 2. Create the camera in the app
`thingino/new-camera` (above) does B and step 3 in one go. By hand, there are
two ways. **B is the real flow**; A is a quicker bench test.

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
curl -sS -X POST https://www.sunrisesunset.studio/api/cameras/provision \
  -H "Authorization: Bearer $CRON_SECRET" -H 'Content-Type: application/json' \
  -d '{"hardware_id":"thingino-<soc -s output>","device_class":"thingino-wyze-v3","label":"wyze-1"}'
```
It returns `camera_id`, `claim_code` and `device_token` (shown once). Put all
three in the config, with `HARDWARE_ID` exactly as provisioned and
`CAMERA_MODEL="wyze-v3"`. Leave `AZIMUTH_DEG` empty. Then open
`https://www.sunrisesunset.studio/setup/<claim_code>` on your phone. The app knows
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

## Finding the status light (`find-status-led`)
Thingino's profiles for the Wyze v3 and Sonoff S2/B1P list only the IR LEDs and
the IR-cut filter, not the front status light. To use that light for feedback,
first find its pin. Copy the script over and run it facing the camera:
```sh
ssh $CAM 'cat > /usr/sbin/find-status-led && chmod +x /usr/sbin/find-status-led' < thingino/find-status-led
ssh -t $CAM find-status-led          # -t: it asks you y/N after each pin
```
It first prints the pins the kernel has claimed (an LED-like name there is a
shortcut), then blinks each unused pin three times, restores it, and asks
whether a light blinked. It skips the pins in `/etc/thingino.json` and anything
claimed by a driver, and never writes to flash. Toggling an unknown pin can
still drop Wi-Fi or reboot the camera: power-cycle and rerun with
`--from <last pin + 1>` (the last pin is saved in `/root/find-status-led.last`).
When it finds the light, it prints the line to add to `thingino.json` and the
`STATUS_LED_PIN` for the agent's config. Please report the pin upstream to
Thingino too.

## Known gaps
- **Aim** comes from the phone app (path B), or is typed by hand (path A). Cameras on their own swivel stand, rather than a window mount, still need a phone-aim step in the app (issue #499 in the app repo).
- **Windows** are computed on the camera. The plan is for the server to send the next window in the heartbeat reply; the agent will prefer that when present (issue in the app repo).
- **`window_id`** uses the UTC date of the sun event, so a Pacific evening sunset carries the next day's date.
- **Packaging**: a setup card installs the agent on stock Thingino (see "Setup card"). A custom Thingino image with the agent baked in (`user/common/overlay/` in the Thingino build) is only needed if the installer's bundled Thingino turns out too old to run the card's `runonce.sh`.
- Directives (`wipe_wifi`, log shipping) and remote updates (`sysupgrade`) aren't handled yet.
