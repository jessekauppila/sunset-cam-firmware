# Sun Auto-Track Aiming — Design

Date: 2026-06-09
Branch: `feat/deploy-aiming-supervisor` (firmware)
Builds on: the v0.4 sun-tap mechanic (validated end-to-end on cam1 2026-06-09) and
the v0.3 sun-self-calibration spec (cloud repo) which first proposed sun-centroid detection.

## Problem

The validated v0.4 flow latches heading from one sun-tap, then flags `suspect`
when the housing tilt drifts >3° from tap-time — which **hides the Confirm
button**. During a handheld setup session every wobble trips it, so aiming feels
broken ("I tap and nothing happens"). Re-tapping after each twist is awkward.

The root cause is the *latch*: heading is frozen at tap-time and goes stale the
moment the camera moves, with no way to track the change (no magnetometer).

## Insight (cross-domain prior art)

Telescope GoTo, spacecraft sun-sensors, and satellite-dish sun-transit alignment
all solve "which way am I pointed?" the same way: the sun at a known time+location
is an absolute azimuth reference, and its pixel position tells you your heading.
Make that **continuous** — detect the sun every frame and recompute heading — and
the camera becomes a live compass: twist it, watch the heading update, no re-tap.

## Goals

1. Continuously detect the sun in the live frame and recompute heading in real
   time, so the operator twists the camera with live feedback and never re-taps.
2. Auto-lock the brightest blob (the sun dominates outdoors); a manual tap
   **overrides** a misdetection (bright cloud, reflection, flare).
3. Keep all validated downstream plumbing (heading math, `/setup/confirm`,
   placement report, supervisor flip) unchanged.

Non-goals: tilt-projection correction for badly-tilted cameras (warn instead;
the mount keeps it near level); multi-day auto-calibration (that's v0.3); lens
distortion correction (v0.3-grade).

## Design

### 1. Detector — `sun_detect.py` (pure, numpy, unit-tested)

```
detect_sun_centroid(gray, rel_threshold=0.92, min_pixels=12) -> (cx, cy) | None
```

- `gray`: 2D numpy array of brightness (0–255).
- Threshold at `rel_threshold * gray.max()`; if fewer than `min_pixels` exceed it,
  return `None` (sun not in frame / clouded).
- Otherwise return the **intensity-weighted centroid** of the bright pixels.
- Pure function, no hardware. Tested with synthetic arrays: bright blob → known
  centroid; off-center blob → correct cx; dim/empty frame → None; two blobs →
  brightest wins (weighted toward it).

### 2. Pi glue — injected `sun_source` (thin, not unit-tested)

A callable that grabs a **downsampled** array via picamera2 (`capture_array`,
strided/resized for speed) under the existing `_cam_lock`, converts to grayscale,
and returns it (or `None`). Throttled to ~2 Hz so the Pi Zero 2 W keeps up with
the 4 fps preview. Injected into `AimingService` like the gyro `reader`, so tests
pass a fake returning canned arrays.

### 3. State model — continuous tracking replaces latch+suspect

`AimingService` gains an optional `sun_source`. On each `state.json` poll
(`_fit_payload`):

- If `sun_source` yields a frame and `detect_sun_centroid` finds the sun:
  recompute `heading = sun_azimuth(now) − pixel_offset_to_angle(cx)`; status =
  **`tracking`**; heading is live. (Still gated on the mount-level check — a
  wildly tilted camera breaks the horizontal-pixel→azimuth assumption.)
- If no sun detected: fall back to the existing tap/heading state
  (`uncalibrated` / `tapped` / `suspect`), so a manual tap still works when the
  sun can't be auto-found.

A manual tap (`/setup/tap`) still anchors heading and, in auto-track mode, acts
as the **override**: it re-seeds which region is "the sun" (v1: simplest form —
a manual tap pins heading from that pixel and pauses auto-track until the sun is
re-detected near there; refine later if misdetection proves common).

`tracking` is a fresh, confirmable state: Confirm is available whenever status is
`tracking` OR `tapped` (no more vanishing button).

### 4. Frontend (`setup_alignment.py`)

- A **"☀ tracking"** badge when status is `tracking` (vs the tilt banner for
  level state).
- The sunset-arc markers + a **sun-dot** at the detected centroid update live as
  the heading changes — twist the camera, watch them move.
- **Confirm enabled** in `tracking` and `tapped`; only hidden in `uncalibrated`.
- Tap still works as override (existing handler + the tap-circle we added).

### 5. Dependency

Add `numpy` to `requirements.txt` (already present on the Pi via picamera2;
needed in the dev venv for the detector + its tests).

## Affected files

- NEW `src/sunset_cam/sun_detect.py` + `tests/test_sun_detect.py`.
- `src/sunset_cam/setup_server.py` — `AimingService` accepts `sun_source`;
  `_fit_payload` runs detection → `tracking`; Confirm allowed in `tracking`.
- `scripts/run-setup-server.py` — wire a real picamera2-backed `sun_source`.
- `src/sunset_cam/setup_alignment.py` — tracking badge, live sun-dot, Confirm
  visibility rule.
- `requirements.txt` — add numpy.

## Testing

- `sun_detect`: centroid correctness, threshold/min-pixels rejection, brightest-
  blob selection, off-center cx. (pure, no hardware)
- `setup_server`: with a fake `sun_source` returning a synthetic sun → status
  `tracking`, live heading; no detection → falls back to tap state; Confirm
  works in `tracking`.
- Manual bench re-run on cam1: point at sun → "☀ tracking", twist → heading +
  markers move live → Confirm anytime → supervisor `mode=capture`.

## Rollout / safety

Auto-track is additive: if `sun_source` is not provided (or detection returns
None), behavior is exactly today's validated tap flow. So this can't regress the
just-validated pipeline — it only adds a better path on top.

## Follow-ups

- Smarter override (tap defines an ROI the tracker prefers).
- Tilt-projection correction for off-level mounts.
- Fold the discrete `suspect` re-tap nag out once tracking is the default.
