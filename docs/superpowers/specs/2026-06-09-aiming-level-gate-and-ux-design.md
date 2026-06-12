# Aiming: mount-referenced level gate + tap UX — Design

Date: 2026-06-09
Branch: `feat/deploy-aiming-supervisor` (firmware)
Extends: cloud-repo spec `docs/superpowers/specs/2026-06-07-pi-alignment-v0.4-sun-tap-aiming-design.md`

> Convention note: the project's pi/aiming specs live in the **cloud repo**
> (`the-sunset-webcam-map/docs/superpowers/specs/`). This one is written in the
> firmware worktree alongside the code it changes, to keep this session isolated
> from the cloud repo's open PRs. Cross-link / relocate into the central
> collection when `feat/deploy-aiming-supervisor` merges.

## Problem

The bench run surfaced it: `HeadingState.apply_tap` refuses a tap unless
`|roll| ≤ 5° and |pitch| ≤ 5°` — hardcoded to a roll-0 mount. But cam1's real
mount reads **roll ≈ -90°, pitch ≈ 0°** when correctly aimed (the MPU6050 chip
is fixed rotated 90° relative to a landscape-level camera). So every tap is
silently rejected (HTTP 422, swallowed by the frontend), the heading never
reaches `tapped`, and the "Confirm aim" button never appears. From the phone it
looks like tapping does nothing. The status badges ("tilted", "tap the sun")
also read like buttons, adding to the confusion.

Confirmed: the camera is **landscape-level**, only the IMU is rotated. So the
horizontal-pixel→azimuth math (`pixel_offset_to_angle` / `heading_from_tap`) is
still correct — this is purely a *level-reference* and *UX-feedback* problem.

## Goals

1. Tap registers when the camera is at its real mount reference (roll ≈ -90,
   pitch ≈ 0), with a **generous ±15° gate** so it isn't fiddly.
2. Clear, live UI feedback telling the operator how to correct the tilt.
3. A persistent marker at the tapped point so the operator can re-tap the same
   spot to refine.

Non-goal (deferred): a real visual polish pass on the aiming page — do that
later with the `frontend-design` skill. This change keeps edits inline in the
existing server-rendered template.

## Design

### 1. Mount reference as a single source of truth (config-driven)

Three values, defaulting to cam1's rig, added to `config.json`:

```json
"mount_roll_ref_deg": -90,
"mount_pitch_ref_deg": 0,
"level_tol_deg": 15
```

Flow: `config.json → resolve_aiming_params → AimingService → HeadingState`, and
also injected into the alignment page as `data-` attributes so the **frontend
badge/banner and the backend gate enforce the identical reference** (no drift
between what the UI says and what the server accepts).

`HeadingState.apply_tap` gate changes from
`|roll| > tol or |pitch| > tol` → refuse
to
`|roll − roll_ref| > tol or |pitch − pitch_ref| > tol` → refuse.

Rationale for config over a hardcoded -90: a future unit could mount the IMU the
other way (+90); a config value means no code change and the default still works
for cam1. (Alternative considered and rejected: hardcode -90 in two files —
simpler but a magic number split across backend and frontend. Auto-calibrate
"capture level" button — more UX/code than needed now; YAGNI.)

Generous ±15° is safe for accuracy because sunset taps sit near the horizon
(vertical center of frame), where roll has minimal effect on the computed
azimuth. The green "level" badge can still reward a tighter mount.

### 2. Red tilt-warning banner

Driven by the existing 200 ms orientation poll:
- **Outside the gate:** red bar — "⚠ Camera tilted — rotate so roll ≈ -90°,
  pitch ≈ 0°" with live values "(now: roll -72°, pitch 3°)".
- **Within the gate:** green — "✓ Ready — tap the sun".

This also resolves the silent-rejection problem: a non-registering tap is
explained by the banner already on screen.

### 3. Tap-point circle marker

On tap, draw an SVG circle at the tapped pixel in the existing `.overlay`; it
**persists** so the operator sees where they aimed and can tap the same spot to
refine. Each new tap moves it. Stays through Confirm.

### 4. Badge re-reference

Re-reference the top "level/tilted" badge to the -90/0 mount (today it would read
"tilted" forever). Status badges remain non-interactive; the red/green banner
makes their role obvious.

## Unchanged (deliberately)

- Azimuth math: `pixel_offset_to_angle`, `heading_from_tap` — correct as-is.
- Drift→`suspect` logic (`update_orientation`, `drift_tol_deg`) — relative to
  tap-time orientation, so the reference doesn't affect it.
- The bottom instruction list — operator confirmed it's good.

## Affected files

- `src/sunset_cam/heading.py` — mount-referenced gate in `apply_tap`.
- `src/sunset_cam/aiming_config.py` — resolve `mount_roll_ref_deg`,
  `mount_pitch_ref_deg`, `level_tol_deg` (with defaults -90 / 0 / 15).
- `scripts/run-setup-server.py` / `src/sunset_cam/setup_server.py` — plumb the
  three values into `HeadingState`.
- `src/sunset_cam/setup_alignment.py` — banner, circle marker, badge
  re-reference, inject reference as `data-` attributes.

## Testing

- `heading.py`: tap accepted at (roll -90, pitch 0); accepted within ±15°;
  refused beyond ±15°; refused at the *old* (0,0) which is now off-reference.
- `aiming_config.py`: the three mount values resolve from config and fall back to
  defaults; existing string-coercion still holds.
- Manual bench re-run: tilt to level on the phone → banner goes green → tap →
  circle appears → Confirm → supervisor flips to `mode=capture`.

## Follow-ups (not in this change)

- Visual polish pass on the aiming page via `frontend-design`.
- Consider surfacing the 422 reason inline at the tap site (the banner covers it
  for now).
