# Prototyping Brief — "Window-Bracket" Phone Onboarding (paste into claude.ai)

> **How to use this:** paste the whole document into a new claude.ai chat and ask it to
> build the interactive prototype as a single-file React artifact. It's self-contained —
> all the domain math, constants, and the real API contract are inline, so the prototype
> can be wired back into the `sunset-cam-firmware` codebase with minimal change. Iterate on
> the UX in the browser, then bring the result back to the Claude Code chat to finalize.

---

## What to build

A **mobile-first, single-file React prototype** (Tailwind ok; no backend) of a new camera
onboarding flow. All device sensors are **mocked with on-screen sliders/toggles** (like a
flight simulator) so it runs in a desktop browser. Where real numbers can be computed
(sun azimuths, bracket angles, coverage), **compute them for real** using the formulas
below — don't fake them. Calm, precise, friendly aesthetic (think a well-made setup wizard,
not a flashy SaaS landing page).

## The big idea

The phone is a **measuring instrument for a physical mounting bracket**, not a stand-in for
the camera. The installer measures the window with the phone; the app outputs a **bracket
wedge angle** + **lens choice** + **where to place the camera in the window**. They fit the
bracket to the Raspberry Pi camera, mount it, and confirm with a live view (and later, when
the sun appears, it auto-confirms). The aim is correct *by construction* — baked into a
piece of plastic — before the camera's weak sensors ever matter.

Core insight the prototype should make tangible: **bracket horizontal angle =
equinox_sunset_azimuth − window_normal_azimuth.** Everything visual is in service of that
subtraction.

## The user flow (screens to prototype)

**Screen 1 — Facing.** Pick sunrise (east) or sunset (west). (Sets whether we use sunset or
sunrise azimuths; sunrise = 360 − sunset.)

**Screen 2 — Measure the window (phone flat on the glass).**
- Instruction: "Hold your phone flat against the window glass, screen toward you."
- The phone's **back camera now faces out the window**, so its compass heading = the
  **window's normal azimuth** (the direction the window looks out). Capture it. Also capture
  phone **pitch** = the glass's tilt from vertical (≈0 for a normal vertical window; nonzero
  for a sloped skylight).
- Mock: a "compass heading" slider (0–359°, magnetic) and a "glass tilt" slider (−15..+15°).
- Show a readout: "This window faces **W (262°)**, vertical." Plus a **viability check**:
  if the window faces too far from the event to ever see it (see solver), warn now.

**Screen 3 — Hinge to the equinox (the AR step).**
- Instruction: "Keep one edge of the phone on the glass and swing the other edge open until
  the moving line meets the **Equinox** line."
- A live **AR-style view** (mock: a simple sky/horizon canvas; real: phone camera) with
  **vertical azimuth guide lines** for Jun-solstice, Equinox, Dec-solstice, and "today",
  projected against the phone's current heading using `azToX` below. As the user "hinges"
  (mock: a heading slider, or drag), the view pans and the lines slide.
- When the phone's heading reaches the equinox azimuth, the Equinox line centers; the user
  **taps to lock**. (The lock is satisfying but the number was already known — this is the
  intuitive realization of the wedge subtraction.)

**Screen 4 — The bracket spec (the novel output).**
- A prominent **"Bracket card"**:
  - **Horizontal wedge: 18° → swing toward S/left** (sign + direction from the solver).
  - **Vertical tilt: 0°** (parameter; default look-at-horizon — expose a small control,
    note it depends on mount height / bracket design).
  - **Lens: wide (102°)** (from `recommendLens(lat)`), with the reason ("the year's sunset
    arc spans 74° here — needs the wide lens").
- A **placement diagram**: a window rectangle with the sunset-arc "cone" (equinox ± HFOV/2)
  drawn over it, and a suggested **camera position within the window** so the frame/mullions
  don't occlude the arc. Coverage readout: "**catches ~341 sunsets/year**" (from `coverage`).
- "If you rotate the aim by N°, you'd catch +M more" — only when the arc doesn't fit the FOV.

**Screen 5 — Mount + confirm (live view).**
- "Fit the bracket to the camera, mount it flush to the glass, power it on." Then a **live
  preview** (mock: placeholder sky; real: `/setup/frame.jpg` snapshot-refresh) with the same
  azimuth guide lines overlaid, so the installer visually confirms the arc sits where the
  bracket predicted.
- Status line: "Provisional aim set. The camera fine-tunes itself to ~1° on the next clear
  sunset." (Sun auto-confirmation happens later, server-side — just message it here.)

## Domain math — implement these for real (JS, copy-ready)

```js
const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;

function julianDay(date) {              // date = JS Date (use UTC y/m/d)
  let y = date.getUTCFullYear(), m = date.getUTCMonth() + 1, d = date.getUTCDate();
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100), b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
}

// Solar declination (deg), NOAA Spencer approx (±~0.5°).
function solarDeclination(date) {
  const n = julianDay(date) + 0.5 - 2451545.0;
  const g = rad((357.528 + 0.9856003 * n) % 360);
  const lam = rad((280.460 + 0.9856474 * n + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) % 360);
  const eps = rad(23.439 - 0.0000004 * n);
  return deg(Math.asin(Math.sin(eps) * Math.sin(lam)));
}

// Sunset azimuth (deg from North, clockwise) at a latitude on a date. Sunset is westward.
function sunsetAzimuth(latDeg, date) {
  const decl = rad(solarDeclination(date));
  let cosA = Math.sin(decl) / Math.cos(rad(latDeg));
  cosA = Math.max(-1, Math.min(1, cosA));
  return (360 - deg(Math.acos(cosA))) % 360;
}
const sunriseAzimuth = (lat, date) => (360 - sunsetAzimuth(lat, date)) % 360;

// The three arc anchors for the AR overlay (year Y). Equinox sunset ≈ 270 everywhere.
function sunsetArc(latDeg, Y) {
  return {
    jun:     sunsetAzimuth(latDeg, new Date(Date.UTC(Y, 5, 21))),   // summer solstice (NW)
    equinox: sunsetAzimuth(latDeg, new Date(Date.UTC(Y, 2, 20))),   // ~270 W
    dec:     sunsetAzimuth(latDeg, new Date(Date.UTC(Y, 11, 21))),  // winter solstice (SW)
    today:   sunsetAzimuth(latDeg, new Date()),
  };
}
// For sunrise-facing, mirror each: riseAz = (360 - setAz) % 360 (equinox → ~90 E).

// Lens horizontal FOV (deg). Identical sensor; lens picked by latitude's arc span.
const HFOV = { wide: 102, standard: 66 };
function recommendLens(latDeg, Y = 2026) {
  const a = sunsetArc(latDeg, Y);
  const span = Math.abs(((a.jun - a.dec + 180) % 360) - 180);
  return span > HFOV.standard ? 'wide' : 'standard';
}

// Coverage: how many days/year the sunset falls within a FOV centered on centerAz.
function coverage(latDeg, centerAz, fovDeg, Y) {
  const half = fovDeg / 2; let count = 0;
  for (let t = Date.UTC(Y, 0, 1); t <= Date.UTC(Y, 11, 31); t += 86400000) {
    const az = sunsetAzimuth(latDeg, new Date(t));
    const d = ((az - centerAz + 540) % 360) - 180;
    if (Math.abs(d) <= half) count++;
  }
  return count;
}
// best_center: brute-force centerAz between the two solstice azimuths to maximize coverage.
// (When the arc fits the FOV, best_center ≈ equinox. When it doesn't — far north — it differs.)

// Magnetic → true. declination is +E (e.g. Bellingham ≈ +15.3°). Real app gets it from lat/lng.
const toTrue = (magHeading, declination) => (magHeading + declination + 360) % 360;

// Project a TRUE-north azimuth to a horizontal screen x for a view centered on centerAz.
function azToX(az, centerAz, fovDeg, width) {
  const d = ((az - centerAz + 540) % 360) - 180;   // signed delta in [-180,180]
  return width * (0.5 + d / fovDeg);                // outside FOV → outside [0,width]
}

// THE BRACKET SOLVER ----------------------------------------------------------
// windowNormalAz: phone-flat-on-glass compass heading (TRUE north).
// targetAz: equinox sunset (or sunrise) azimuth from sunsetArc().equinox.
// Returns the horizontal wedge the bracket must add to swing the camera from the
// glass normal onto the target. Sign: + = swing clockwise (toward the larger azimuth).
function bracketHorizontalWedge(windowNormalAz, targetAz) {
  return ((targetAz - windowNormalAz + 540) % 360) - 180;   // signed, [-180,180]
}
// Viability: a wedge beyond ~±65° means the window frame/glass occludes the view —
// the window faces too far from the event. Warn the user to try another window.
function windowViable(wedgeDeg, hfovDeg) {
  return Math.abs(wedgeDeg) <= 65 - 0;   // (could also require the arc edges within reach)
}
// Vertical tilt: parameter. Default 0 (camera looks at the horizon, where the sun sets).
// For elevated mounts a few degrees down-tilt; exact value depends on the bracket design
// (being designed separately). Expose as a control; don't hard-code geometry yet.
```

## Mocking the sensors (simulation panel)

Mirror how the existing firmware wizard mocks things. Provide a small "simulation" panel:
- **Latitude** slider (e.g. 25–60°N), default **48.75** (Bellingham). Drives all the math.
- **Window facing** = compass-heading slider (0–359°, magnetic) for screen 2.
- **Glass tilt** slider (−15..+15°), default 0.
- **Hinge heading** slider for screen 3 (sweeps the AR view).
- **Declination** number, default **15.3** (the app normally derives it from lat/lng).
- Toggles: "wide vs standard lens" (or let `recommendLens` decide), "show today's line".

## Real API contract (so it drops back into the codebase)

The prototype's data shapes should match these real endpoints (served by the Pi at
`/setup/*`; in the cloud deployment they become `/api/devices/{id}/*` — only the URLs
change). Keep your mock functions returning these shapes:

```
GET  /setup/arc-azimuths?facing=west|east   → { jun, equinox, dec, today }   // TRUE north deg
GET  /setup/coverage?heading=<deg>          → { captured, best_center_az, captured_at_best,
                                                fits, summer_az, winter_az }
GET  /setup/frame.jpg                        → one JPEG (snapshot-refresh preview; poll ~600ms)
GET  /setup/state.json                       → { status, has_mpu, roll_deg?, pitch_deg?,
                                                sun_fx?, sun_fy?, heading_deg?, fits? }
POST /setup/heading  { heading_deg, source:'phone'|'window'|'manual', roll_deg?, pitch_deg? }
POST /setup/tap      { fx, fy }              → { heading_deg, fits }
POST /setup/confirm  {}                      → { status:'confirmed', placement }
```

NEW endpoints this flow will add (design them in the prototype as mocks; we'll build them
back in firmware/cloud afterward):

```
GET  /setup/window-solve?normal_az=<deg>&tilt=<deg>&facing=west|east
        → { window_normal_az, target_az, horizontal_wedge_deg, vertical_tilt_deg,
            lens:'wide'|'standard', hfov_deg, viable:bool, captured, best_center_az }
POST /setup/bracket-confirm  { window_normal_az, glass_tilt_deg, horizontal_wedge_deg,
                               vertical_tilt_deg, lens, facing }
        → { status:'bracket_spec_recorded', ... }   // records the measured placement (coarse)
```

Reuse the existing AR projection constants from the wizard: `HFOV_PI = 102`,
`HFOV_PHONE = 60` (phone-camera FOV used only for the AR overlay projection), and the
azimuth-line projection `x = width*(0.5 + d/fov)` (see `azToX`). Magnetic→true uses
`webkitCompassHeading` (magnetic) + declination on real iOS.

## Open questions worth exploring IN the prototype

1. **Vertical tilt / altitude.** What down-tilt (if any) best frames the sunset for a typical
   sill/elevated mount? Try a control + a side-view diagram. (Couples to the bracket geometry
   being designed separately.)
2. **Equinox-center vs best_center.** Show coverage for the equinox-centered aim AND the
   computed `best_center`. They match when the arc fits the FOV (the common, lens-selected
   case) and diverge far north — make that legible, don't hide it.
3. **Window-placement guidance.** How to render "put the camera *here* in the window" so the
   frame/mullion doesn't clip the arc cone — a simple top-down or front diagram.
4. **Bracket readout format.** What's the clearest way to state "18° wedge toward the left"
   so someone can pick/print/3D-print the right bracket without confusion (handedness!).
5. **Failure/edge messaging.** Window faces too far off; arc bigger than any lens; sloped
   glass; southern hemisphere (flip the NW/SW intuition).

## Non-goals for the prototype

- No real backend, auth, or device comms — all mocked.
- Don't design the physical bracket's mechanical form (separate chat); just output the
  *angles* it must realize.
- Don't worry about the cloud HTTPS hosting / pairing — that's a separate build.

## When you're done

Bring the React artifact (or its key components + the chosen UX decisions) back to the Claude
Code chat. We'll: thread real `lat/lng` + lens from device config, implement `/setup/window-solve`
+ `/setup/bracket-confirm` in `setup_server.py` (TDD), add the bracket-solver math to
`solstice_math.py`, and fold the new screens into `web/setup-wizard/` alongside the existing
methods.
