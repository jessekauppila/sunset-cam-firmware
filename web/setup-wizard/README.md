# Setup wizard v2 — cloud-first, phone-first (handoff to Claude Code)

Vanilla HTML/CSS/ES-modules, no build step. Home is the CLOUD app over HTTPS:
installer scans the QR on the housing → lands here with the device in the URL
→ the cloud relays the camera's preview and sends captured aim down as
set-aim directives.

## Run it

    cd setup-wizard
    python3 -m http.server 8080
    # open http://localhost:8080/?mock=1

Mock-mode sim panel now covers the new world: **unit has the optional MPU**
(toggles the progressive-enhancement level hints in sun/window), sun-detection
failure, phone heading slider, **phone held tilted** (exercises the tilt chip).

## What changed from v1 (firmware-reality redesign)

1. **Phone-first.** "With your phone" is the recommended card. The phone,
   mated to the housing, supplies BOTH heading and tilt — capture sends
   `{ heading_deg, source:'phone', tilt:{pitch,roll} }`. The leveling UI is
   the phone's own sensors: a non-blocking "✓ held upright / ⚠ tilted — we
   record the tilt either way" chip in the AR stage.
2. **No global level gate, MPU optional.** Sun and window methods never block
   on level. If `state.has_mpu`, they show a live level hint (sun: slim chip;
   window: the dashed horizon line goes live); if not, instructional copy
   stands alone ("Set it level on the sill — eyeballing it is fine"). Sun
   panel copy: "the camera should sit roughly at its mounted position."
3. **Self-refine is the promise.** Phone/window/manual aims are marked coarse;
   the confirm screen says "starting at ≈N° — the camera fine-tunes itself to
   about 1° on the next clear sunset/sunrise." Window card subtitle leans in.
4. **Clipped = fits===false** (whole-year arc doesn't fit the FOV). Copy:
   "this aim won't catch the whole year's sunsets — nudge toward center."
   Applied uniformly: sun, tap, phone-verify, manual.
5. **True north.** All headings sent/displayed are true north. The AR loop
   converts: `true = (webkitCompassHeading + declination) % 360`, declination
   from the cloud (device lat/lng); +15.3°E fallback.
6. **HTTPS assumed.** No secure-context gating. The phone card disables only
   if the browser genuinely lacks DeviceOrientation (desktop), with the reason
   shown.

## Panel → endpoint map (api.js, all TODO(bridge-doc))

Device-scoped base: `/api/devices/{id}` (id from QR → URL).

| Panel / action               | Call                                     |
|------------------------------|------------------------------------------|
| Relayed preview              | `GET {base}/preview` (img-compatible; if WS-pushed frames, swap attachStream only) |
| Sun detect + MPU level hints | poll `GET {base}/state` → status/has_mpu/roll/pitch/sun_fx/fy/heading_deg/fits |
| Tap fallback                 | `POST {base}/aim/tap {fx,fy}`            |
| Phone / window / manual aim  | `POST {base}/aim {heading_deg, source, tilt?}` |
| AR + verify markers          | `GET {base}/arc-azimuths?facing=` — true-north Jun/Equinox/Dec/today from device lat/lng + date |
| Declination                  | `GET {base}/declination`                 |
| Confirm                      | `POST {base}/aim/confirm {heading_deg, method, facing, coarse}` |

## Flagged for firmware (not built, no wizard UI impact)

**Optional MPU ↔ sun alignment on first refine.** When the first clear sun fix
arrives (orientation known to ~1°), units with the MPU can use it as a
calibration moment — in this direction: the sun calibrates the MPU, not the
reverse. (1) Zero the MPU's tilt bias against the sun-derived orientation, so
the MPU becomes a trusted movement/bump detector during cloudy stretches
between sun fixes. (2) Log phone-captured tilt vs sun truth as a diagnostic on
mating/install quality across the fleet. Not needed for aim — the sun fix
supersedes both phone tilt and MPU tilt — so this is a background behavior,
decide-in-firmware. The wizard already supplies its input (tilt rides along on
phone-source aim).

## Known gaps for the wiring pass

- `HFOV_PI=102` and `HFOV_PHONE=60` constants — thread real values (config
  hfov; measure a phone or read from camera capabilities).
- Tilt convention: portrait-upright assumed (beta≈90 ⇒ pitch=beta−90,
  roll=gamma). Verify sign/axes against what firmware expects, on-device.
- Verify-stage markers render client-side at HFOV_PI; if the relayed preview
  already burns in a server-side arc, pick one source to avoid double-drawing.
- Quick field test for declination sign + vertical-pose compass: capture
  toward a known landmark, compare.
- No state restore on reload mid-wizard (flow is under a minute; add if QR
  re-scans should resume).
