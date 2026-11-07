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

- **Wyze v3 SD flashing** (corrected 2026-11-07): the current installer is a whole-card image, `wyze-cam-3/wyze-cam-3-sd.zip` in https://github.com/wltechblog/thingino-installers (one `sd.img`: MBR + FAT32 holding Wyze's factory boot file `factory_t31_ZMC6tiIDQN` and three Thingino images). Write it with `thingino/prepare-sd wyze-cam-3`, insert with the camera unplugged, power on, wait 3–4 min for the `THING-…` Wi-Fi. No button press. It backs up the stock firmware to `WYZE_BACKUP_*/combined_backup.bin` on the card (unique per camera; keep it to revert). The image is rebuilt only occasionally, so `sysupgrade -f` after first boot. The older `demo_wcv3.bin`-on-FAT32 method is not what this installer uses.
- **Wyze v3 has several boards** (`wyze_cam3_t31x_gc2053_atbm6031`, `..._t31al_gc2053_atbm6031`, `..._t31x_gc2053_rtl8189ftv`), but the installer carries all three and picks the matching one itself, so there's nothing to identify before flashing. Record which one it chose after first boot (`/etc/os-release`).
- **Sonoff box the user has is the CAM-B1P** (outdoor bullet, 2K, 108° H FOV, motorized 180° pan). Thingino profile `sonoff_b1p_t23n_sc2336_atbm6012bx` includes the pan motor (`gpio_pan "54 52 53 64"`, 2000 steps), a white light on GPIO 59, IR850 on 50, SD card detect on 49. **An SD installer for the B1P now exists** (`sonoff-outdoor-b1p/sonoff-outdoor-b1p-sd.zip`, with a video; power it from a plain power-only USB-C cable; it backs up the stock firmware to `backup/`). Sonoff has disabled the easy unbrick paths, so a failed flash needs a CH341A programmer; the case has no visible screws (elektroda thread). Still flash it last.
- Thingino's Wyze v3 and Sonoff profiles map **no status LED** (only IR + IR-cut); that's why `find-status-led` exists.
- Thingino tools available on-camera: `curl`, `jct` (JSON), `prudyntctl snapshot -c 0` (JPEG to stdout), `gpio set|info|list`, `crond`, `sysupgrade`, writable overlay root.
- App side: a camera needs a `cameras` row + paired `webcams` row. Quick path: `scripts/tier0-create-camera.sh` (prod DB). Real path: `POST /api/cameras/provision` (CRON_SECRET) → claim code + token → phone wizard `/setup/<claim>` → `pre-register` sends aim → heartbeat says `ready`.

## Plan

### Phase 1: Wyze v3 on the bench (do first)
1. ~~Identify the board variant~~ (not needed, see above); the installer is `wyze-cam-3-sd.zip`.
2. Done: `thingino/prepare-sd` (macOS only) downloads the installer, writes it to a card it has checked is removable, after you type the disk id, verifies the write, and can stage the agent (`--stage-agent`, `--conf`). Linux support not written.
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
