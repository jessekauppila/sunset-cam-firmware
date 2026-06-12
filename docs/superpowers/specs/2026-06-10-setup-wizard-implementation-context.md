# Setup Wizard — Implementation Context (answers from the code)

Date: 2026-06-10
Bridges the design-mockup wizard spec to the real firmware. Answers its "Open
questions 1–6" + the inline TBDs from `setup_server.py`, `heading.py`,
`solstice_math.py`, `sun_detect.py`, `aiming_config.py`, `setup_alignment.py`.

## ⚠️ Read this first: two architecture facts that reframe the wizard

1. **The setup UI is moving to the cloud (HTTPS).** Decision 2026-06-10
   (`2026-06-10-cloud-served-https-setup-design.md`). The endpoints below are the
   **firmware-local HTTP** forms that exist *today*. Build/iterate the wizard
   against these on the local page first, but in production each becomes:
   - MJPEG preview → **relayed frames** (Pi → cloud).
   - `POST /setup/*` → a **`set-aim` directive** down the control plane.
   - `orientation.json` / `state.json` → **relayed telemetry**.
   **Step 3b (phone AR) only works in the cloud-served HTTPS page** — it needs
   `getUserMedia` + the compass, both blocked on the Pi's HTTP. So 3a/3c/3d run
   on the local page today; **3b is gated on the cloud-served build.**

2. **Two cameras.** 3a (by the sun), 3c (window), and 3b-stage-3 (verify) use the
   **Pi's** camera (its MJPEG + its server-side sun detection). 3b-stage-2 uses the
   **phone's** camera (`getUserMedia`) + the **phone's compass**; the captured
   heading is the phone's compass heading (= camera heading via the mated unit),
   POSTed as a heading. Arc overlays differ accordingly (see Q6).

## Q1 — Endpoints (current firmware-local shapes)

All served by `setup_server.AimingService` on the Pi at `:8080`.

| Purpose | Method/Path | Request | Response |
|---|---|---|---|
| Page | `GET /` or `/setup/align` | — | HTML |
| Live IMU | `GET /setup/orientation.json` | — | `{roll_deg, pitch_deg}` |
| Aim state (poll) | `GET /setup/state.json` | — | fit payload (below) |
| Live preview | `GET /setup/preview.mjpg` | — | multipart MJPEG (~4 fps) |
| Tap the sun | `POST /setup/tap` | `{pixel_x, pixel_y}` (pixel_y ignored; pixel_x in natural-image width space) | 200 fit payload **or** 422 `{status:"uncalibrated", error:"level the camera first"}` |
| Set heading (phone/manual/window) | `POST /setup/heading` | `{heading_deg, source}` (`source`="phone"\|"manual", telemetry only) | 200 fit payload **or** 422 off-level |
| Confirm | `POST /setup/confirm` | `{}` | 200 `{status:"confirmed", placement:{azimuth_deg, tilt_deg, roll_deg, confirmed_at}}` **or** 409 `{status, error:"aim not set — tap the sun first"}` |

**There is no separate "sun detect" endpoint.** Detection runs server-side in
`_track_sun` and is surfaced via `state.json`: when the sun is found (and the mount
is level), `status` becomes **`tracking`** with `sun_fx`/`sun_fy` (0..1) and a live
`heading_deg`. So "☀ finding the sun…" = **poll `state.json` until `status==="tracking"`**.

**Fit payload** (`state.json`, and the 200 body of tap/heading):
```
{ status: "uncalibrated"|"tracking"|"tapped"|"suspect",
  roll_deg, pitch_deg,
  sun_fx, sun_fy,                 // only when status==="tracking"
  heading_deg, fits,             // only when a heading exists
  summer_az, winter_az, captured, best_center_az, captured_at_best }
```

## Q2 — Magnetic vs true north (RESOLVED: backend is TRUE north)

Every azimuth in the pipeline is **geographic / true north**: `compute_sun_azimuth`,
`sunset_azimuth_for_day`, `sunset_arc_azimuths`, `az_to_pixel`, `fov_fit`. `apply_heading`
stores whatever degrees you POST and compares them against these true-north azimuths.
**So `/setup/heading` expects true-north compass degrees.**

iOS `webkitCompassHeading` is **magnetic** (true only if the page has location access).
→ **The client must convert before POSTing:** `heading_true = (heading_magnetic +
declination) % 360`. Bellingham/Seattle declination ≈ **+15.3°E (2026)**. Best: compute
declination from lat/lng (WMM model) in the **cloud** and apply it. Never send raw
magnetic. Document this at the capture site.

## Q3 — Does every method need roll ≈ -90°? (only WITH an MPU)

> **Updated 2026-06-11 — MPU is now optional** (`2026-06-11-mpu-optional-decision.md`).
> The level gate below applies **only when an MPU is present**. With **no MPU**,
> `_orientation()` returns the mount reference (assume level), so the gate **passes**
> and aiming proceeds; tilt comes from the **phone** (mated) at install. Phone
> onboarding is the primary path and needs no on-device IMU. The text below describes
> the MPU-present behavior.


`apply_tap` **and** `apply_heading` both gate on:
`abs(roll − mount_roll_ref) ≤ level_tol AND abs(pitch − mount_pitch_ref) ≤ level_tol`,
with config defaults **mount_roll_ref = -90, mount_pitch_ref = 0, level_tol = 15**.
(cam1's IMU is mounted rotated 90°, so "level" reads roll **-90**, not 0.)

So **sun, phone, window, and manual all require the camera within ±15° of (roll -90,
pitch 0).** Implications:
- The window flow's level check **is** this gate. Draw the dashed reference line
  relative to **roll = -90**: tilt error = `roll + 90`; green when `|roll+90| < tol`
  and `|pitch| < tol`.
- **Surface "level the camera" inline on a 422 from ANY method**, not just window.
- ⚠️ **Mismatch with the wizard's 3a ("no leveling required"):** the code *does*
  require rough level for the sun method, and roll genuinely affects the
  pixel→azimuth mapping (a rolled camera shifts the horizontal axis). To make 3a
  truly leveling-free you'd need to add **roll-correction** to `pixel_offset_to_angle`
  (project the tap through the roll angle). Until then, 3a needs rough level + the
  sun in the Pi's frame. Decide: keep a lenient level requirement on 3a, or build
  the roll-correction (a real, scoped firmware task).

## Q4 — Sun-detection latency + the "clipped" condition

- **Detection:** `detect_sun_centroid(gray, abs_floor=230, rel=0.9, min_pixels=12)` on
  a **stride-8 downsample** of `capture_array("main")` (1920×1080 → ~240×135), run
  inside `_track_sun` on each `state.json` poll. Latency ≈ one poll (sub-second on a
  Pi Zero 2 W; the `capture_array` dominates). Not separately measured — poll
  `state.json` ~500 ms during the sun step for a snappy feel.
- **"Clipped" = `fits === false`** in the payload (from `fov_fit`: the *full-year*
  sunset arc doesn't fit the FOV at this heading). NOT "outer 8% of frame" (mockup
  stand-in). Note `fits` answers "will this aim catch the whole year's sunsets," which
  is the meaningful aim-quality signal. If you specifically want "tap too near the
  edge → re-tap nearer center," that's a *different* check on `sun_fx` (e.g.
  `|sun_fx − 0.5| > 0.4`); decide which "clipped" you mean.

## Q5 — hfov config vs FOV_DEG=102 (UNIFY — there are two sources)

- **Heading math** uses **config `hfov`** (`aiming_config` default `102.0` →
  `AimingService.hfov_deg` → `pixel_offset_to_angle` / `heading_from_tap` / `fov_fit`).
- **Overlay/AR arc** uses the module constant **`FOV_DEG = 102.0`**, embedded as
  `data-fov`.
- Both are 102 today so they agree — but they're **two sources** → drift risk. The
  Arducam IMX708 **Wide is ~120°** (per the v0.3 spec); if you bump config `hfov` to
  120 for accuracy, the overlay still uses 102 → arcs land wrong.
- **Fix (recommended, small):** thread the config `hfov` into `render_align_page` and
  embed `data-fov = hfov` (instead of `FOV_DEG`); use it for AR positioning. One FOV,
  driven by config. Also: **confirm the real camera FOV (102 vs 120)** and set it in
  config once.

## Q6 — Solar-arc source for the phone AR overlay

Server-side math exists and should be the single source:
- `sunset_arc_azimuths(lat, year)` → `(summer, equinox, winter)` **sunset** azimuths.
- Sunrise = mirror: `rise_az = (360 − set_az) % 360` (equinox: sets 270 / rises 90).
  Add a `sunrise_arc_azimuths` helper or mirror client-side based on Step-1 facing.
- `compute_sun_azimuth(lat, lng, t_utc)` → live "today" sun-dot azimuth.
- `az_to_pixel(az, center_az, fov, width)` → pixel (center_az = the phone/cam heading).

Phone AR (3b stage 2) runs **client-side on the phone**. Two options:
- **(Recommended) Cloud computes, client renders:** the cloud knows lat/lng/date →
  compute the 3 arc az's (set or rise per facing) + the live sun az, send them down;
  the client positions arcs via `az_to_pixel` against the **phone compass heading**.
  Single source of truth; port `solstice_math` to TS once in the cloud.
- Or port the ~15-line `compute_sun_azimuth` + arc math straight to client JS.

The Pi-view arcs (3a / verify) already use the server heading via the overlay we
built — reuse `data-arc-*` + `positionArc()` in `setup_alignment.py` as the reference
implementation.

## Other TBDs answered
- **IMU poll endpoint/rate:** `GET /setup/orientation.json`; current page polls 200 ms.
- **Window level tolerance:** `level_tol` (config default **15°**), referenced to roll -90.
- **Confirm field that drives the "aimed" badge:** `state.json.status` (`tapped`/`tracking`)
  + `heading_deg`; after `POST /setup/confirm`, the 200 body is `{status:"confirmed", placement}`.
- **MJPEG reload trap:** the wizard's "one `<img>`, set/clear `src` per panel, backoff on
  `onerror`" is exactly right — it fixes the infinite-stream wedge we hit.

## Recommended small firmware fixes — DONE (2026-06-10)
1. ✅ **FOV unified** (Q5): `render_align_page(hfov_deg=...)` now emits `data-fov = hfov`,
   fed from `AimingService.hfov_deg`. Overlay + heading math share one FOV. (Still set
   the *real* lens FOV — 102 vs the Arducam Wide's ~120 — in config.)
3. ✅ **`sunrise_arc_azimuths`** (Q6): mirror of the sunset arc (rise = 360 − set), for
   the east-facing/sunrise wizard path.
2. **3a leveling — RESOLVED as a decision (no code now):** keep the **lenient ±15° gate**
   for the sun method in v1. The camera is installed at a fixed mount (roll ≈ -90) and
   within ±15° near the horizon the roll-induced azimuth error is small (and the sun
   self-refine corrects residual error). So **soften the wizard 3a copy** from "no
   leveling required" → "the camera should sit roughly at its mounted position." Full
   roll-correction in `pixel_offset_to_angle` (project the tap through the roll angle) is
   a **deferred enhancement**, only needed if truly tilt-free sun-aim becomes a goal.
