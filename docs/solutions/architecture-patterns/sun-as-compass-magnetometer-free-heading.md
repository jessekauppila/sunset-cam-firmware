---
title: Sun-as-compass — derive (and continuously track) heading without a magnetometer
date: 2026-06-10
category: docs/solutions/architecture-patterns
module: pi-firmware-aiming
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - You need a device's true compass heading but have no magnetometer/GPS module (only an accel/gyro for tilt)
  - A celestial reference (the sun) is visible in the camera frame at a known time + location
  - The operator aims by twisting the device and needs live feedback
tags: [aiming, azimuth, computer-vision, sun-sensor, heading, telescope-goto, no-magnetometer]
---

# Sun-as-compass — derive (and continuously track) heading without a magnetometer

## Context
The sunset camera (Pi + Arducam + an IMU that only gives roll/pitch) needs its true
compass heading to aim at the sunset — with no magnetometer or GPS. The same problem
is solved across telescope GoTo alignment, spacecraft sun-sensors, and satellite-dish
sun-transit pointing: the sun at a known time+location is an absolute azimuth
reference, and its pixel position in frame tells you where the device points.

## Guidance
Two levels, both worth knowing:

1. **One-shot (sun-tap):** `heading = sun_azimuth(now, lat, lng) − pixel_offset_to_angle(tap_x)`.
   Cheap, exact at the moment of the tap. Valid only while the device doesn't move —
   no sensor tracks yaw afterward.

2. **Continuous (sun auto-track) — the magic version:** detect the sun centroid every
   frame (threshold the saturated blob → intensity centroid, ~30 lines of numpy) and
   recompute heading each poll. The device becomes a live compass: twist it, watch the
   heading update, no re-tapping. This is the spacecraft-sun-sensor / telescope-GoTo
   pattern. Keep the manual tap as an override for misdetection (bright cloud, glare).

Detector returns centroid in *frame* pixel space; `pixel_offset_to_angle` only depends
on `cx / frame_width`, so it's resolution-independent — no scaling to capture width.
Still gate on the mount being roughly level (the horizontal-pixel→azimuth mapping
assumes the sensor axis is horizontal).

## Why This Matters
A magnetometer is ±5–15° and fails near metal; the sun fix is ~±1°. Continuous tracking
also dissolves the latch-and-nag UX trap (see
[[dont-let-a-staleness-state-hide-the-primary-action]]). Make it additive: if no sun is
detected, fall back to the tap flow so cloudy installs still work.

## When to Apply
Compass-free aiming of any camera/antenna where a bright celestial reference is in view.
Note the obvious limitation that drove a follow-up idea: **it needs the sun.** For
overcast installs, pair it with a phone-magnetometer heading hand-off as an alternate
setup path.

## Examples
- `detect_sun_centroid(gray, abs_floor=230, rel=0.9, min_pixels=12)` → `(cx, cy) | None`
  (None when no saturated region — flat/cloudy frame).
- `state.json` exposes `status: "tracking"` + `sun_fx`/`sun_fy` (0..1) so the page draws
  a live dot and a live heading as the operator twists.
