# Decision: the MPU6050 is OPTIONAL — phone-first onboarding

Date: 2026-06-11
Status: Accepted. Firmware change landed (reader optional).
Affects: phone-compass/heading-sources spec, setup-wizard bridge doc, v0.3 sun
self-calibration, BOM.

## Decision

The MPU6050 (gyro/accel) moves from a **required** component to an **optional,
Tier-2 "verify/robustness"** sensor. **Phone onboarding is the primary install path.**

## Why

The MPU only ever provided **roll/pitch (tilt)** — never heading (no magnetometer).
Its jobs were: (1) the on-device level gate, (2) bump/drift detection, (3) `tilt_deg`
in the placement. In the **mated-unit phone flow**, the phone supplies *both* heading
(compass) and tilt (accelerometer) at the moment of capture, so the MPU is **redundant
at install**. Its only unique remaining value is **continuous on-device tilt after the
installer's phone is gone** — and even that has a substitute: **v0.3 sun
self-calibration** re-derives full pose (heading + tilt) from clear-sky sun
observations.

Making it optional removes a component, the soldering, the I2C setup, the entire
**gyro-wake bug class**, and a field-failure surface (it was also the part lit during
the 2026-06-10 dead-board debugging). Simpler, cheaper, more manufacturable.

## Tiering

```
Tier 1 — Install (MPU-free, default):  phone (mated) → heading + tilt → recorded aim
Tier 2 — Ongoing verify:
   • no MPU:   v0.3 sun self-calibration catches drift on clear days
   • + MPU:    instant on-device tilt → immediate bump detection + a live level
               check for the sun/window methods (optional robustness / pro SKU)
```

## Accepted tradeoff

Without an MPU: the **non-phone methods lose their live on-device level check** (tap-the-sun
and place-in-a-window rely on the operator's eye + the housing `↑ UP` marker), and
**bump detection waits for the next clear sunset** instead of being instant. For a
rigidly-mounted sunset camera that doesn't move after install, this is acceptable — the
phone verified it at install, and the sun self-corrects.

## What changed (firmware — done)

- `AimingService.reader` is now **optional** (`None` allowed). `_orientation()` returns
  the **mount reference** (assume level) when there's no IMU *or* on a transient read
  error — so the level gate **passes** instead of blocking aiming. (Previously a
  missing/erroring MPU returned `(0,0)`, which failed the -90 mount gate and bricked the
  whole flow.)
- `run-setup-server.py` wraps the MPU init in try/except → `reader=None` if no I2C/MPU.
- Net: a unit with **no MPU** runs the full aiming flow; phone/manual headings are
  accepted; `tilt_deg` in the placement defaults to the reference.

## Follow-ups

- ✅ **Accept phone-supplied tilt** (done 2026-06-11): `/setup/heading` takes optional
  `roll_deg`/`pitch_deg`; with no MPU they're recorded in the placement and the gate
  enforces them — giving the phone method a real level check without an IMU.
- **v0.3 sun self-calibration** is the MPU-less drift/tilt recovery path — promote it
  from "follow-on" to the default ongoing-verify mechanism.
- BOM: mark the MPU optional / a pro-tier add-on.

## Spec deltas

- **phone-compass-and-heading-sources** + **setup-wizard implementation-context (Q3)**:
  the "roll ≈ -90 gate on all methods" now reads "…**when an MPU is present**; with no
  MPU the gate is skipped (assume mounted level) and tilt comes from the phone."
- **cloud-served-https-setup**: sensing-stays-on-device still holds, but tilt sensing is
  now optional; the phone is the install-time tilt source.
