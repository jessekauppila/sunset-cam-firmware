# Thingino camera bring-up: handoff for a local Claude Code session

Written 2026-11-07 at the end of a cloud session. Read this first, then the PRs.
This work needs a local machine: writing SD cards, reaching cameras on the home
LAN over SSH, and someone standing at the camera.

## Where things are

| What | Where | State |
|---|---|---|
| Shell agent for Thingino cameras (`sunset-agent`), init script, config template, first-camera test plan | this repo, `thingino/`, PR #17 (`feat/thingino-agent`) | open, tested under dash against a mock server; never run on hardware |
| Status-light pin finder (`find-status-led`) | `thingino/find-status-led`, PR #17 | open, tested against a fake gpio/sysfs |
| Printed window wedge mount (OpenSCAD) | `hardware/window-wedge-mount.scad`, PR #17 | open; FOV ray-checked |
| Setup wizard: fixed-lens cameras (camera model, FOV, printed-mount step) | `the-sunset-webcam-map` PR #502 (`feat/thingino-camera-models`) | open, CI green, not tried on a phone |
| Phone aim for cameras on their own stand | app issue #499 | idea |
| Server sends next capture window in heartbeat | app issue #500 | idea |
| Laser-cut box mount (only top/bottom wedge plates change with angle; side blinders; engraved back plate; 2 orange kusabi pins) | mock-ups only, not in a repo yet | needs laser bed size, acrylic thickness, kerf, and measured camera heads |

## Facts already established (don't re-research)

- **Wyze v3 SD flashing** uses a file named `demo_wcv3.bin` in the root of a FAT32 card (Wyze recommends 32 GB), inserted with the camera unplugged; hold the setup button while plugging in, 3–6 s. Thingino's Wyze v3 installer uses this mechanism; get the installer from https://github.com/wltechblog/thingino-installers and read its notes on stock-firmware versions.
- **Wyze v3 has several boards**: Thingino profiles `wyze_cam3_t31x_gc2053_atbm6031`, `..._t31al_...`, `..._rtl8189ftv`, `..._rt5370`. Check which one the camera is before choosing an image (installer notes / `ipctool`).
- **Sonoff box the user has is the CAM-B1P** (outdoor bullet, 2K, 108° H FOV, motorized 180° pan). Thingino profile `sonoff_b1p_t23n_sc2336_atbm6012bx` includes the pan motor (`gpio_pan "54 52 53 64"`, 2000 steps), a white light on GPIO 59, IR850 on 50, SD card detect on 49. **No confirmed SD-card installer for the B1P**; the case has no visible screws (elektroda thread). Don't flash it until an installer is confirmed.
- Thingino's Wyze v3 and Sonoff profiles map **no status LED** (only IR + IR-cut); that's why `find-status-led` exists.
- Thingino tools available on-camera: `curl`, `jct` (JSON), `prudyntctl snapshot -c 0` (JPEG to stdout), `gpio set|info|list`, `crond`, `sysupgrade`, writable overlay root.
- App side: a camera needs a `cameras` row + paired `webcams` row. Quick path: `scripts/tier0-create-camera.sh` (prod DB). Real path: `POST /api/cameras/provision` (CRON_SECRET) → claim code + token → phone wizard `/setup/<claim>` → `pre-register` sends aim → heartbeat says `ready`.

## Plan

### Phase 1: Wyze v3 on the bench (do first)
1. Identify the board variant; download the matching Thingino installer.
2. Write `thingino/prepare-sd` (macOS + Linux): find the SD card safely (refuse internal disks, confirm by size/name), format FAT32, copy the right installer, and optionally stage `sunset-agent`, `S99sunset-agent` and a filled-in `sunset-agent.conf` for copying after first boot. Never `dd` to a guessed device.
3. Flash, finish Thingino setup (Wi-Fi, root password, SSH), run the checks in `thingino/README.md` step 1.
4. Run `find-status-led`; record the pin.
5. Create the camera (tier0 first), install the agent, run `sunset-agent heartbeat`, `snap`, `windows`; then a full sunset window. Pass criteria are in `thingino/README.md`.
6. Fix whatever the real hardware breaks; push to PR #17.

### Phase 2: claim-code + phone setup
Provision via the API, open `/setup/<claim>` on a phone with PR #502 deployed to a preview, print or cut the mount, submit, confirm the agent goes `ready` and captures. Then merge #502 and #17.

### Phase 3: agent features
- Status light: off around each snapshot, Pi light language otherwise (`the-sunset-webcam-map/docs/hardware/2026-06-16-feedback-light-and-aim-integrity-spec.md`).
- Bake the agent into a custom Thingino image (`user/common/overlay/`), config from the SD card.
- Issue #500 (server-computed windows).

### Phase 4: Sonoff B1P
Confirm an SD installer exists. If yes: flash, then add pan control to the agent (aim at the day's sunset azimuth; outdoors, no window needed). If no: leave it on stock firmware.

## Repo conventions
App repo: read its `CLAUDE.md` (worktrees via `scripts/wt.sh`, explicit `git add`, arm auto-merge rather than pressing Merge, apply migrations before merging code that reads them). Jesse merges PRs.
