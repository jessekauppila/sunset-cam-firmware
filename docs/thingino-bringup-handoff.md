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
- **Wyze Cam _Pan_ v3 is on hold — it is NOT the Cam v3** (resolved 2026-11-08). The bench unit the user already owns is a Pan v3 (see the memory note), but Phase 1 needs the *plain Cam v3* he's buying. The Pan v3 has no SD installer, its stock SD recovery (`recovery_wyzepan3.bin`) is reported broken on this model, and no restore path can be proven before the first write, so flashing it today is a write-without-net gamble. Full verdict and the conditions to revisit: `docs/thingino-pan-v3-flash-handoff.md`. Thingino *does* support the hardware (profile `wyze_campan3_t31x_gc2053_atbm6031`, secureboop, DFU, pan/tilt motors mapped), so it's a "later," not a "never."
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

## Camera roadmap: which Wyze model, when (resolved 2026-11-08)

Four Wyze options came up; this is the order that trades risk for capability.
Full Pan-v3 reasoning and sources: `docs/thingino-pan-v3-flash-handoff.md`.

1. **Wyze Cam v3 — now (Phase 1).** `t31x`, 1080p. Mature, prebuilt images,
   reversible SD install, our `prepare-sd wyze-cam-3` + README test plan already
   built around it. The de-risking vehicle: prove the whole pipeline here.
2. **Wyze Cam v4 — image-quality upgrade (optional, later).** `t41`, 2.5K,
   ATBM6062 wifi, 16 MB flash. SecureBoot defeated Oct 2026; SD-installable
   *today* (`wyze-cam-4` in wltechblog, reversible), but only on Thingino master
   / no prebuilt update stream yet, and two sensor variants (os04d10 confirmed,
   gc4653 not). Good step up in frames, no panning. Not worth it for the *first*
   camera.
3. **Wyze Cam Pan v3 — if panning is wanted sooner.** `t31x` + pan/tilt, profile
   in-tree, but **no installer, broken stock SD recovery, no provable restore
   path** — the brick-risk research project. Tracked in issue #19.
4. **Wyze Cam Pan v4 — the north-star target (Jesse's real goal).** `t32nq` +
   **SC835HAI 4K sensor** + **ATBM6162S** wifi, 16 MB NOR, 360° pan/tilt + AI
   tracking. FCC ID `2AUIUWYZECPAN4` (2025-08-19). **Note the SoC is T32N — a
   different chip and a different crack from the Cam v4's T41**, so "build on the
   v4 defeat" does not transfer. Instead it has its *own* live effort:
   - Thingino **already boots on it** (builds labelled `master+…, 2026-11-05`;
     live-unit bugs #1925/#1933, profile fixes PR #1946).
   - A **no-open-case SD installer exists**: `github.com/gtxaspec/wyze-campan4-sd-install`,
     which bypasses the stock U-Boot RSA-PSS signature via **CVE-2026-46728**
     (FIT hashed-nodes clone) and is *designed* to dump + SHA256-verify the full
     16 MB NOR before writing.
   - **But it is bricking today** (issue #1927, 2026-11-06): the backup came out
     useless (only the 192 KiB u-boot partition, rest 0 KiB) and recovery needed
     the SPI flash pins held + a web-flash. So the verified-backup safety is not
     actually working yet.
   - **Verdict: the Pan v4 is the target, and it is moving fast — but do not
     flash it until #1927 is fixed and the gtxaspec installer's verified backup
     demonstrably produces a full 16 MB dump.** Watch that repo + Thingino's
     campan4 issues. Horizon tracked in its own issue.
   - Pan v4 console for the CP2102 UART: **`ttyS1`, 115200 8N1** (per #1927).

## Repo conventions
App repo: read its `CLAUDE.md` (worktrees via `scripts/wt.sh`, explicit `git add`, arm auto-merge rather than pressing Merge, apply migrations before merging code that reads them). Jesse merges PRs.
