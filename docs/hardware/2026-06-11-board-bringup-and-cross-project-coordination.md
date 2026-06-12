# 2026-06-11 — New board bringup, wizard on hardware, + cross-project coordination

Resume anchor. Branch `feat/deploy-aiming-supervisor` (firmware). Continues the
2026-06-10 marathon.

## What happened tonight
- **New Pi Zero 2 W board** (the old one died) transplanted with the SD + camera. This
  time a **narrower Arducam IMX708 (75° diagonal ≈ 66° HFOV)** instead of the wide.
  Power clean (`throttled=0x0`).
- **The setup wizard ran on real hardware for the first time** — served by the firmware
  at `http://<pi>:8080/`, wired to `/setup/*`. Sun **tracking**, tap, window, manual,
  and confirm all work end-to-end on the device.
- **Features shipped this session** (on the branch): IMX708 **lens profiles** with
  latitude auto-pick (wide vs standard); the **/setup/frame.jpg snapshot-refresh** preview
  (iOS can't render MJPEG); **window/manual never level-gated** (escape hatch);
  **/setup/coverage** + a confirm-screen "where it points / sunsets per year / rotate for
  +N more" panel; **has_mpu** in state; **phone-supplied tilt**; the wizard bundle served
  from `web/setup-wizard/`.
- **Decisions:** MPU optional / phone-first; phone-AR primary (no video relay) — the
  cloud layer rescoped to a lightweight HTTPS page + heading hand-off.
- **Hiccups → learnings** (docs/solutions): deploy-needs-restart, iOS-MJPEG→snapshot,
  never-gate-the-escape-hatch, don't-hand-edit-device-JSON. (The night's biggest time-sink
  was a stale un-restarted service.)

## Device-specific notes for THIS board
- **MPU is mounted FLIPPED** vs the old board: reads roll **≈ +90** when level (old read
  -90). Config set to `mount_roll_ref_deg: 90`. (Per-device calibration — should be
  provisioned, not hand-set; see memory `provision-per-device-config-not-nano`.)
- **lens: standard** set in config. At Bellingham (48.75°N) the year's sunset arc (74°)
  exceeds this lens (66°), so `fits=false` near the solstices — expected; a northern site
  wants the wide lens. Auto-pick would recommend wide; this bench unit overrides to standard.
- Currently in **AIMING/setup mode**, not capturing. The `capture_window_*` in config is
  expired (2026-06-07) — update it (or let the cloud drive it) to capture.

## Cross-project coordination (the bigger picture)
This camera is the **live test material** that unblocks parallel work:
- **Web app PRs (in `the-sunset-webcam-map`), both ready, awaiting a live custom camera:**
  - **#64** — "My Cameras" map (owner globe, health rings). Merge first.
  - **#65** — per-camera detail page `/cameras/[id]` (stacked on #64; auto-retargets to
    main after #64).
  - Both need a **signed-in smoke test against a real camera reporting data** — exactly
    what this board becomes once it's registered + POSTing snapshots/heartbeats.
- **Two parked firmware branches** (separate worktrees), tested on Mac, awaiting **one
  live golden-hour run on a Pi** to retire both:
  - `feat/thermal-telemetry` @ `32ae1fa` (temp/throttle sampler, 88 tests)
  - `feat/golden-hour-exposure` @ `059ae27` (biased-auto exposure, 80 tests)
  - Gotchas: use `python3.11 -m pytest` locally (system python3 is 3.9); worktree convention.

## To make this camera live for the web smoke tests
1. Finish/confirm an aim (any method) → cloud flips placement to `ready`.
2. Update the capture window (or let the cloud/cron drive it) so it captures in the
   sunrise/sunset window.
3. Supervisor → `mode=capture` → it POSTs snapshots + heartbeats → appears on #64's globe
   (health-ringed) → click → #65 detail page. Then the A+B smoke tests run against it.

## Open / next
- Merge story for `feat/deploy-aiming-supervisor` (this PR) — gated historically on v0.4
  real-sun accuracy; now also the primary setup surface. Real-sun aim accuracy is still
  the one unrun hardware check (sun had set tonight).
- **Cloud HTTPS hosting** of the wizard (unlocks phone-AR + remote install) — the last big
  build, in `the-sunset-webcam-map`.
- Validate the two parked firmware branches with a golden-hour run on this board.
- `~/Documents/Claude Sessions/ongoing/` is TCC-locked from this environment — checkpoints
  go in the repo (here) instead.
