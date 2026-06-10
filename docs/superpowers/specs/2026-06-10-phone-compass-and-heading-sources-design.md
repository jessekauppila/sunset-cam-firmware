# Phone-Compass Install + Heading-Source Abstraction — Design

Date: 2026-06-10
Branch: `feat/deploy-aiming-supervisor` (firmware)
Builds on: validated v0.4 sun-tap + sun-auto-track (2026-06-10). Extends the aiming
flow so the *heading source* is pluggable while the `confirm → placement` pipeline
(already validated end-to-end on cam1) is unchanged.

## Problem

Sun-based aiming (tap or auto-track) needs the **sun in frame** — useless during a
cloudy install (the real PNW blocker). We need install methods that work in any
weather, without making a second visit, and without a second precise pipeline.

## Insight

The phone the installer is already holding has a **magnetometer + GPS**. If the
phone's heading can be transferred to the camera, you get a compass-free,
sun-free heading. And every heading source can feed the **same** downstream flow:
`heading → overlay shows the sunset arc → adjust/verify → Confirm → placement`.

## Goals

1. **Heading source becomes pluggable**: sun-track (built), **phone-compass**, and
   **manual dial**, all feeding the one validated pipeline.
2. **Phone-compass via a mated unit**: hold phone + camera together (Pi/lens out the
   front); the housing is shaped so the phone nests **flush + parallel to the lens
   axis**, so the phone's compass heading *is* the camera heading — no sighting skill.
3. **Compose accuracy**: phone-compass (~5–15°, any weather) is a coarse day-one
   bootstrap; **sun auto-track silently refines it to ~1°** on the next clear sunset.
4. Manual dial as the always-available floor.

## Design

### 1. Heading-source abstraction (backend)

A heading can now be **anchored three ways**, all converging on the same confirmable
state:
- **sun-tap** (`apply_tap`) — existing.
- **sun-auto-track** (`_track_sun`) — existing; live `tracking`.
- **direct** (`apply_heading`) — NEW: a caller supplies the heading degrees directly
  (from the phone compass or a manual dial).

`HeadingState.apply_heading(heading_deg, roll_deg, pitch_deg) -> bool`:
- Gated on the mount-level check (same as `apply_tap` — the overlay math assumes a
  level mount).
- Sets `_heading = heading_deg % 360`, records tap-time roll/pitch, status → `tapped`
  (a confirmable heading; the existing drift→`suspect` still applies and is fine here).

New endpoint `POST /setup/heading {heading_deg, source}`:
- `service.handle_post("/setup/heading", body)` reads live orientation, calls
  `state.apply_heading(float(body["heading_deg"]), roll, pitch)`, returns the fit
  payload (so the overlay updates immediately), or 422 "level the camera first".
- `source` ("phone" | "manual") is recorded for telemetry; behavior is identical.

`_current_aim` precedence stays: **auto-track (sun) wins when detected**, else the
anchored heading (from tap/phone/manual). So if the sun later appears, it overrides
and refines the coarse phone heading automatically — that *is* the self-refine.

### 2. Frontend — a heading-source panel

On the setup page, a small panel offering the three sources:
- **Manual dial** (works today over HTTP): a compass dial / number input → `POST
  /setup/heading {source:"manual"}`. The overlay then shows the sunset arc; the
  operator nudges until framed; Confirm.
- **Phone compass**: a "Use my phone's compass" button. On tap (user gesture),
  request `DeviceOrientationEvent.requestPermission()` (iOS), read
  `webkitCompassHeading` (iOS) / `alpha` w/ `absolute` (Android), show it live, and a
  "capture heading" button → `POST /setup/heading {source:"phone"}`.
- **Sun**: the existing tap / auto-track path.

Capture-held-then-verify flow: aim the mated unit, capture heading, mount the camera,
then the **live sunset-arc overlay** confirms/adjusts framing (and the sun refines
later). No need to hold perfectly still.

### 3. Known constraint — DeviceOrientation needs HTTPS

The `DeviceOrientation` API requires a **secure context**. The Pi serves the setup
page over plain HTTP (`http://<host>:8080`), where iOS Safari blocks the compass.
So in v1:
- **Manual dial works now** over HTTP (no API needed) — ship it.
- **Phone-compass UI is built but gated**: it feature-detects a secure context and,
  if absent, shows "phone compass needs HTTPS — using manual for now." Solving the
  HTTPS story (self-signed cert on the Pi, or a localhost-secure-context trick, or
  routing setup through the cloud) is a **follow-up**, tracked here, not in this slice.

### 4. Hardware ask (out of firmware scope, tracked)

The housing needs a flat **phone-mating reference surface** aligned to the lens axis
so the mated-unit mechanic is exact. Folds into the existing up-arrow/housing work;
the IMU continues to supply tilt (roll/pitch), the phone supplies azimuth.

## Affected files (this slice)

- `src/sunset_cam/heading.py` — `apply_heading`.
- `src/sunset_cam/setup_server.py` — `POST /setup/heading`.
- `src/sunset_cam/setup_alignment.py` — heading-source panel (manual dial now,
  phone-compass behind the HTTPS feature-gate).
- Tests for `apply_heading` (gate, sets heading, confirmable) and the endpoint.

## Testing

- `heading.apply_heading`: accepted at mount-level → status `tapped`, heading set;
  refused off-level; heading normalized mod 360.
- `setup_server`: `POST /setup/heading {heading_deg: 250}` → 200, fit payload with
  `heading_deg≈250`; confirm then succeeds; off-level → 422.
- Frontend render: panel + `/setup/heading` + secure-context feature-gate present.
- Manual (later, on hardware): manual dial → overlay → confirm → `mode=capture`;
  phone-compass once HTTPS is solved.

## Rollout / safety

Purely additive — sun tap/track unchanged; with no `apply_heading` call the behavior
is exactly today's validated flow. The phone-compass UI degrades to manual when the
secure-context check fails, so HTTP installs still get a working manual path.

## Follow-ups

- HTTPS / secure-context for the Pi setup page (unblocks live phone compass).
- Record `source` into the placement report for fleet telemetry.
- Auto-refine UX: when the sun later overrides a phone heading, surface "aim
  upgraded to sun-precision" so the installer sees the self-correction.
