# Bracket Onboarding — Integration Design

Date: 2026-06-12
Repos: `sunset-cam-firmware` (solver math, setup endpoints, the React wizard in
`web/setup-wizard/`) + (later) `the-sunset-webcam-map` (HTTPS hosting of the wizard so
the phone's sensors work).

Accompanies the prototype + handoff (`window-bracket-prototype.jsx`,
`window-bracket-handoff.md`, v19-aligned) and the prototyping brief
(`2026-06-12-window-bracket-onboarding-prototype-brief.md`). This is the design-of-record
for bringing the prototype into the codebase.

## The idea (unchanged from the prototype)

The phone is a **measuring instrument for a physical mounting wedge**, not a camera proxy.
Measure the window's facing with the phone → output a wedge angle (snapped to a manufactured
ladder) + flip direction + lens → fit the wedge between case and glass → aim is correct by
construction. Spine: `wedge = equinox_azimuth − window_normal_azimuth`, snapped to the ladder;
the lens FOV + the sun's later self-calibration absorb the residual.

## Decisions

1. **Bracket flow is THE primary onboarding path.** sun / phone-AR / window / manual become
   fallbacks for odd cases.
2. **React comes into the wizard.** Adopt React + a minimal build step (Vite). Rationale:
   the claude.ai ↔ Claude Code prototype loop stays near copy-paste. Built bundle is static —
   the Pi and the cloud serve it the same way; only a `build` step is added.
3. **Honor the v19 corrections** (do NOT reintroduce): no vertical tilt; no ±65° gate
   (advise, never block); discrete wedge ladder via one `WEDGE_MAX`; `flip_direction = null`
   at 0°; camera on 4× M2 standoffs in the lid; vertical glass only.
4. **Reuse existing solar math; add only the new bits.** `solstice_math.py` already has the
   declination / sunset-azimuth / arc / `az_to_pixel` equations matching the prototype. NEW:
   `bracket_horizontal_wedge` (one angle diff), `snap_wedge` (the ladder), ladder constants.
5. **Recorded aim is coarse → the sun refines it.** Placement recorded with `source='bracket'`,
   `coarse=true`, plus wedge/offset/residual; existing sun self-calibration absorbs the snap
   residual.
6. **Coverage is computable now (first-order).** Use `count_sunsets_in_fov(lat,lng,aim_az,fov,
   year)` for a real sunsets/year figure, labeled pre-vignetting; the bracket-side refinement
   (lens-hole vignetting) sharpens it later. (Turns the prototype's `TBD` into a number.)

## Parameterize the uncertain values (so external answers slot in without rework)

- **Lens horizontal FOV.** The prototype uses `HFOV.wide = 120`, but **120° is the IMX708
  wide lens's *diagonal* spec; ~102° is its *horizontal* FOV**, and the sunset arc spans
  horizontally. The firmware uses `LENS_HFOV = {"wide":102,"standard":66}`. **Action: confirm
  the wide lens's true *horizontal* FOV with the bracket chat**; thread `hfov` from device
  config / `aiming_config` into the solver and the page (don't hardcode 120). Recommendation
  doesn't change at Bellingham; the coverage figure + AR scale do.
- **Wedge ceiling.** One constant `WEDGE_MAX` (prototype = 20°, ladder 0–20 step 5). The
  brackets may go to ~45°. Keep it a single config value; bumping it regenerates the ladder.
- **Flip-direction handedness sign.** "Tall end toward north/south" from the offset sign is
  mirror-flippable exactly once and fails silently. Verify against the bracket chat's raw JSON
  for a non-zero example (the 12°-north case) before trusting the label.

## API (firmware `setup_server.py`)

NEW (host-agnostic pure logic):
```
GET  /setup/window-solve?normal_az=<deg>&facing=west|east
  → { window_normal_az, window_azimuth_offset_deg, window_offset_side,
      target_az, wedge_angle_deg, flip_direction, residual_aim_error_deg,
      aim_az, lens, hfov_deg, captured, poor_fit }
POST /setup/bracket-confirm
  body { window_normal_az, window_azimuth_offset_deg, window_offset_side,
         wedge_angle_deg, flip_direction, residual_aim_error_deg,
         lens, material_thickness_mm, facing }
  → { status:'bracket_spec_recorded', placement }
```
Notes:
- **`window_normal_az` (or `aim_az`) MUST be in the confirm payload** — the prototype's payload
  omits it, but the server needs it to record the placement heading
  (`aim_az = normal_az + signed_wedge`). Add it.
- `lens` serialized as `"wide_120"` | `"standard_66"` (or revised per the FOV confirmation).
- `bracket-confirm` records placement: heading=`aim_az`, `source='bracket'`, `coarse=true`,
  carrying wedge/offset/residual for the record.

EXISTING (reuse, don't rebuild): `/setup/arc-azimuths?facing=` (confirm it handles
`facing=east` via `sunrise_arc_azimuths`), `/setup/frame.jpg` (snapshot-refresh preview),
declination (cloud-computed; local fallback ~15.3). Shared AR projection: `az_to_pixel` /
`azToX`, true-north = magnetic + declination.

## Architecture / files

- **`src/sunset_cam/solstice_math.py`** — add `bracket_horizontal_wedge`, `snap_wedge`,
  `WEDGE_STEP`/`WEDGE_MAX`/ladder. (TDD; reuse existing azimuth fns.)
- **`src/sunset_cam/aiming_config.py`** — thread `hfov` resolution into the solver; confirm
  the wide value.
- **`src/sunset_cam/setup_server.py`** — add `/setup/window-solve`, `/setup/bracket-confirm`;
  extend placement recording with `source='bracket'`. (TDD.)
- **`web/setup-wizard/`** — becomes a **React app** (Vite). The 6 bracket screens (port the
  prototype) are the primary path; sun/phone/window/manual ported as fallbacks (phased). Keep
  the shared machinery (arc fetch, declination, true-north, `azToX`, snapshot-refresh preview).
- **Build/serve:** add `npm run build`; the Pi's static serve + the cloud host both serve the
  built bundle.

## Hard dependency: HTTPS hosting for the phone sensors

The bracket measurement uses `deviceorientation` (compass) + `getUserMedia` (camera), which
require a **secure context**. The Pi serves HTTP, so the **real-phone** bracket flow must be
**cloud-HTTPS-hosted** (see `2026-06-11-phone-first-onboarding-decision-and-plan.md` and the
`phone-sensor-apis-need-https` learning). `localhost` is a secure context for dev, but a phone
hitting the Pi's IP over HTTP is not. → The backend math + endpoints and the React app with
**mocked** sensors are fully buildable/testable now; **real phone sensors** wait on the
cloud-HTTPS setup hosting.

## Phasing (proposed build order)

1. **Backend math + endpoints (TDD), host-agnostic.** `bracket_horizontal_wedge`,
   `snap_wedge`, ladder; `/setup/window-solve` + `/setup/bracket-confirm`; `source='bracket'`
   placement; first-order coverage. Parameterize `hfov` + `WEDGE_MAX`. *Fully testable now.*
2. **React-ify the wizard + wire the bracket flow to the real endpoints**, sensors still
   mockable (the prototype's sim panel). Ships as the primary path against mocked sensors.
3. **HTTPS hosting + real phone sensors** — depends on the cloud-served setup page build.
4. **Port legacy methods** (sun/phone/window/manual) into the React wizard as fallbacks.
5. **Bracket-side refinements** (external): real coverage w/ vignetting, confirmed wedge
   ceiling, verified flip handedness, standoff-surface default.

## External (bracket chat / hardware) — can't resolve from code

- Wide lens true **horizontal** FOV. — Wedge **ceiling** (20→~45). — **Flip handedness** sign
  (need a non-zero raw JSON example). — **Coverage** with lens-hole vignetting. — **Standoff
  surface** (lid vs base; prototype assumes lid).
