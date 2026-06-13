# Window-Bracket prototype → Claude Code handoff (v19-aligned)

Accompanies `window-bracket-prototype.jsx`. Working single-file React prototype of the
6-screen onboarding flow, sensors mocked behind sliders, real solar math inline. This
note is the part a code paste can't carry: what's real, what's mocked, what's a decision
vs. a placeholder, and what to wire. It reflects the **v19 bracket spec** — an earlier
draft assumed features the bracket never had (see "Corrections" below); this supersedes it.

## The big idea

The phone is a measuring instrument for a physical mounting wedge, not a camera proxy.
The installer measures the window's facing with the phone; the app outputs which wedge
(from a fixed ladder) + flip direction + lens. They fit the wedge between the case and
the glass, tape it up, and the aim is correct by construction. Spine: one subtraction,
`wedge = equinox_azimuth − window_normal_azimuth`, snapped to the manufactured ladder.

## Screens

1 facing → 2 measure window (phone flat on glass) → 3 hinge to equinox (AR, demo→live)
→ 4 bracket spec → 5 assemble → 6 mount & confirm.

## Real vs. mocked (don't re-derive the real parts)

REAL, copy-ready — port to `solstice_math.py` as-is:
- `solarDeclination`, `sunsetAzimuth`/`sunriseAzimuth`, `arcAnchors`, `azToX`,
  `bracketHorizontalWedge`, `snapWedge`, `recommendLens`.
- Verified: Bellingham 48.75°N → arc Jun 307° / Eq 270° / Dec 233°, span 74° → wide lens.
- Contract round-trips against the bracket chat's worked example: a window 12° off due
  west → 10° wedge, 2.0° residual. (Confirmed by calc.)

MOCKED — replace when wiring:
- All sliders (lat, window facing, hinge heading, declination). Real lat/lng/declination
  come from device config; declination computed cloud-side.
- Step-3 "live mode" is the hinge slider standing in for `deviceorientation` — see below.
- Live views on screens 3 and 6 are placeholder sky; real = phone camera (getUserMedia)
  and the relayed Pi preview.

## Corrections folded in from v19 (do NOT reintroduce these)

The bracket only ever had these features; an earlier handoff invented the rest:
- **No vertical tilt.** Fixed level (horizon). No collar, no second axis, no compound
  angle. Removed the field entirely — it controlled nothing.
- **No ±65° viability gate.** That number was the lens half-FOV, conflated with a bracket
  angle. Windows are never hard-blocked; past the ladder they get a "still works, aimed
  as close as the part allows" advisory.
- **Wedge ladder is fixed discrete steps, not a 5°/10° unit choice.** Currently
  0–20° in 5° steps. ONE constant — `WEDGE_MAX` — controls the ceiling.
- **Handedness → flip direction.** One mirror-symmetric part per angle; flipping the pair
  reverses aim. Installer language: "install with the tall end toward [north/south]." At
  0° flip_direction is `null` (flat, symmetric) — the UI must NOT ask "which side?" there.
- **Lens is 120° wide** (was 102°).
- **Coverage (sunsets/year) is NOT computed.** Shown as TBD. The real figure needs
  (window offset, wedge angle, true 120° FOV, lens-hole vignetting) — bracket-side only.
- **Camera mounts on 4× M2 standoffs in the lid** (lens out the front hole), optical axis
  perpendicular to the lid, so case aim = camera aim. No "ring"/"seat" — that was invented.
- **Sloped glass unsupported.** Vertical windows only (VHB-flush assumes a vertical plane).

## Output contract (the payload screen 6 prints)

Minimal, matches the bracket chat's v19 contract:

    { window_azimuth_offset_deg, window_offset_side, wedge_angle_deg,
      flip_direction, residual_aim_error_deg, lens, material_thickness_mm }

- `flip_direction` is `null` at 0°.
- `lens` is `"wide_120"` | `"standard_66"`.
- `material_thickness_mm` defaults 3.0 (cut files are parametric on it).

## Demo→Live (the one subtle thing to port carefully)

`HingeAnim` runs a rAF-tweened instructional loop until real phone movement appears, then
becomes a live instrument. Trigger: movement > 3° from a captured baseline. In the
prototype "phone heading" is the hinge slider; the prop it feeds is

    liveOpenDeg = angDiff(currentHeading, capturedWindowNormal)

On a real phone that's identical — `currentHeading` from `deviceorientation`
(webkitCompassHeading, magnetic → true via declination), `capturedWindowNormal` from
screen 2. The component needs ZERO logic changes; only the data source swaps. Display
clamps opening to 52° for sanity; lock math stays exact. (SMIL was replaced with rAF on
purpose — React remounts broke SMIL's document clock; don't reintroduce `animateTransform`.)

## What needs real wiring (maps to the brief's API contract)

NEW endpoints (mocked as pure functions here):
- `GET  /setup/window-solve?normal_az=&facing=` → the screen-4 bundle (wedge angle,
  flip direction, residual, lens, offset).
- `POST /setup/bracket-confirm { …the payload above }`.

EXISTING: `/setup/arc-azimuths` (needs the sunrise mirror), `/setup/frame.jpg`
(snapshot-refresh preview), `/setup/declination`. Solver math → `solstice_math.py`;
endpoints → `setup_server.py` (TDD); screens fold into `web/setup-wizard/` beside the
existing methods.

## Open questions to resolve WITH the code / hardware

1. **Wedge ceiling.** Prototype ships 0–20° (`WEDGE_MAX = 20`, one-line bump). The
   brackets may physically go to ~45°. The bracket chat needs to confirm the real max and
   what limits it (material / VHB shear at steep angles / lens-hole occlusion). This isn't
   just SKU count — a higher ceiling makes far more real-world windows first-class instead
   of compromises, which changes screen-2's advisory tone.
2. **Flip-direction sign.** The prototype labels "tall end toward north/south" from the
   azimuth-offset sign. This is the one thing only the physical part can confirm — it's
   mirror-flippable exactly once and wrong silently. Ask the bracket chat for the raw JSON
   of a NON-zero example (the 12°-north case they offered) and diff it against the UI.
3. **Coverage.** Let the bracket chat compute sunsets/year properly; the UI is honest
   about TBD until then, but a real number beats a blank.
4. **Standoff surface default.** Prototype says lid (serviceable). Confirm vs. base.

## Relationship to the other setup wizard

There's an earlier cloud-first / phone-first wizard (`setup-wizard.zip`) with four
calibration methods (sun, phone-AR, window, manual). The brief says these bracket screens
"fold into `web/setup-wizard/` alongside the existing methods" — so the bracket flow is
likely a NEW METHOD within that wizard, not a replacement. They share machinery: AR
projection (`azToX`), arc-azimuth endpoint, declination handling, true-north conversion.
Don't rebuild those. Decide with the user: new top-level method, or the new default path?

## Suggested first message to Claude Code

"Here's the window-bracket onboarding prototype (JSX) + this handoff note, aligned to the
v19 bracket spec. Don't re-derive the solar math — it's verified; port it to
solstice_math.py as-is. Read the note's 'Corrections' so you don't reintroduce vertical
tilt / the ±65° gate / handedness (the part doesn't have them). Then implement
/setup/window-solve and /setup/bracket-confirm (TDD) against the payload in the prototype,
and fold the six screens into web/setup-wizard/ as a new method alongside sun/phone/window/
manual — reusing the shared AR + azimuth + declination machinery rather than duplicating
it. Finally, answer open questions 1–4 from the codebase/hardware where you can, and flag
anywhere my mocked shapes don't match reality."
