# Decision + Plan: phone-AR-primary onboarding, no video relay, sun refines

Date: 2026-06-11
Status: Accepted. Supersedes the frame-relay design in
`2026-06-10-cloud-served-https-setup-design.md` (now rescoped).

## Decision

The **default, confidence-first onboarding is phone-AR**, using the **phone's own
camera + compass** (held mated to the housing), not a Pi→phone video relay. Aim
coarsely-but-smoothly on the phone; the **sun refines the heading to ~1° afterward**
on the Pi; the optional MPU watches tilt/drift.

## Why

- **The phone's camera is instant; a Pi→phone relay is laggy.** Continuous
  "swing-to-aim" only feels confident with zero lag → use the phone's camera.
- Coarse-but-smooth beats precise-but-janky for the *install moment*; precision is
  recovered automatically by the sun afterward, so the installer never sweats it.
- The phone does all the AR locally (its camera, its compass, client-side projection),
  so **no video ever needs relaying** — which deletes the heaviest part of the old
  cloud plan.

## Two-phase workflow

```
Phase A — coarse, smooth, ON THE PHONE (default):
  mated phone → phone camera + AR sun-path + phone compass → swing to aim →
  capture heading (true-north). Mount the camera.
Phase B — precision, ON THE PI, after mounting (background):
  the SUN calibrates the true heading to ~1° (v0.3 self-calibration);
  the optional MPU watches tilt + bumps between sun fixes. Shim to dial in.
```

Precision split (important): **the sun gives the precise heading** (it's the only
absolute azimuth reference); **the MPU gives tilt + bump detection only** (no compass).

## What's already built (in the wizard, `web/setup-wizard/`)

- Phone-AR with `getUserMedia` (phone camera) + `DeviceOrientation`/`webkitCompassHeading`
  + iOS `requestPermission` + magnetic→true declination correction.
- Arc azimuths fetched once, projected client-side against the live compass heading
  (smooth, no per-frame server call). "With your phone" is the recommended card.
- The Pi-served tap-the-sun / window / manual methods (firmware `/setup/*`), wired.
- MPU optional (no-IMU assumes level); phone-supplied tilt recorded.

## Rescope of the cloud layer (drop the relay)

The cloud-served deployment's job shrinks to a **lightweight HTTPS page + a heading
hand-off**, NOT a frame-relay pipeline:
- Serve the wizard over **HTTPS** (so the phone's camera/compass APIs work).
- Compute **arc-azimuths + declination** from the device lat/lng (it already has them).
- **Record the captured heading** as the camera's placement (→ the supervisor flips to
  capture on its next heartbeat). The Pi doesn't "apply" a heading for the phone path —
  the aim is physical (mounting); the heading is recorded metadata.
- If a remote operator wants to *see* the Pi's view, use **occasional snapshots**, not
  a live stream. No `multipart` relay.

## Plan (what's left, in order)

1. **Firmware (now, this slice):** record `source` + `coarse` on the placement so the
   cloud/map knows a phone/window/manual aim is coarse (→ eligible for sun refine) vs a
   sun aim (precise). TDD. *(Executed in this change.)*
2. **Cloud (next, `the-sunset-webcam-map`):** host the wizard over HTTPS at
   `/setup/{code}`; `arc-azimuths` + `declination` endpoints; a `record-aim` endpoint
   that writes the placement. Reuses the control-plane auth.
3. **Phase B — v0.3 sun self-calibration (device-dependent):** detect the sun across
   sunset observations, solve the precise heading, supersede the coarse aim. Validates
   the "supreme accuracy" promise. Needs a live camera (the new board).
4. **Polish:** thread real `HFOV_PHONE` (measure) + `HFOV_PI` from config; tilt
   sign/axis check on-device.

## Not doing

- The Pi→cloud **live video relay** (deleted — the phone uses its own camera).
- Forcing phone-AR over the Pi's local HTTP (it needs HTTPS; on-site local installs use
  the sun-tap method instead, which is precise anyway).
