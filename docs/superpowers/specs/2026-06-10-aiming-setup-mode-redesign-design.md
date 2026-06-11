# Aiming Setup-Mode Redesign — branched flow + world-locked AR sun-lines

Date: 2026-06-10
Branch: `feat/deploy-aiming-supervisor` (firmware)
Brief: memory `aiming-setup-ui-needs-ia-redesign`; builds on the validated heading
sources (sun-tap, sun-auto-track, phone-compass/manual) and the existing
`setup_alignment.py` render.

## Problem

The setup page grew by accretion into one confusing scroll: action and feedback are
in different places, there's no guided flow, buttons are silent, badges look
tappable, the MJPEG preview wedges reload, and the solstice markers are a static
screen-locked diagram rather than true AR. (Full list in the brief memory.)

## Design

### Flow (branched, smart-recommended)

```
1. QR on housing → phone opens setup for THIS camera ({code})
2. "How do you want to aim?"  (smart-recommend, all three shown)
     ☀  Use the sun        — recommended when the sun detector finds a sun in frame
     🧭 Use my phone        — any weather; hold phone+camera as one mated unit
     🪟 Just pick a window  — quickest; west / east / both (coarse)
3. Method screen → all converge on ONE shared screen:
     the LIVE PREVIEW with world-locked AR sun-lines + action-adjacent Confirm
4. Confirm → placement → "✓ Aimed. The sun will fine-tune it automatically." → done
```

Smart-recommend uses the existing `detect_sun_centroid` on a live frame: sun found →
pre-highlight "Use the sun"; else pre-highlight "Use my phone." The user can always
pick another. (Decision 2026-06-10: smart-recommend, let them change.)

### The shared confirm screen (the backbone — build first)

Every method ends here; the method only supplies the *initial heading*.
- **Live preview** with the **world-locked AR sun-lines** (below).
- **Action-adjacent feedback**: the heading readout, "✓ heading set," and the Confirm
  action all live *here*, next to the preview — not split top/bottom.
- **Confirm** commits → placement → success state, all in view.

### World-locked AR sun-lines (the centerpiece)

Replace the screen-locked solstice diagram with real AR:
- Compute the solstice (Jun/Dec) and equinox sun*set* and sun*rise* azimuths for the
  location.
- Place each at `az_to_pixel(az, heading, fov_deg, width)` where `heading` is the
  **live** heading (auto-track) or the captured static heading (phone/manual).
- **Re-render every state poll** — as the camera pans under auto-track, the sun moves,
  the heading updates, and the lines slide to stay on their true azimuths. Real AR,
  only possible because of the continuous-heading work.
- **Off-frame bearings** get an edge arrow + label ("← winter sunset, 25° left") so the
  installer knows which way to turn.
- Labels/colors distinguish solstices vs equinoxes, set vs rise.

### Per-method screens (thin; reuse the backbone)

- **Sun**: live preview + "tap the sun" / "☀ tracking" (existing) → backbone.
- **Phone**: "hold phone + camera together, aim at the horizon, capture heading"
  (DeviceOrientation; HTTPS-gated) → heading set → backbone to verify → Confirm.
- **Window**: pick W / E / Both → coarse heading (facing center az) via
  `/setup/heading` → backbone.

### Reload-safe preview

The infinite MJPEG `<img>` wedges reload. Options (decide during build): tear the
stream down on navigation, or switch to a periodic snapshot refresh
(`/setup/frame.jpg` every N ms) for the non-aiming screens. Keep MJPEG only where live
motion matters.

## Build approach

Inline HTML/CSS/JS in `setup_alignment.py` (no framework), built with
**`ce-frontend-design` + `agent-browser`**: render `render_align_page` (and new
sub-renders) to a temp HTML with mock state, load in a browser, screenshot, iterate on
composition/hierarchy/copy/AR positioning. Verify against the live page before done.

**Build sequence:**
1. **AR sun-lines on the shared confirm screen** (highest visual value, self-contained,
   fixes the worst feedback-locality problem). Backend: a `/setup/state.json` already
   carries heading; add the solstice/equinox azimuth set (or compute client-side from
   lat/lng already in the page).
2. Method-choice entry + smart-recommend.
3. Per-method screens.
4. Reload-safe preview.

## Affected files

- `src/sunset_cam/setup_alignment.py` — the redesigned render (likely split into
  per-screen sub-renderers as it grows).
- `src/sunset_cam/solstice_math.py` — expose solstice+equinox set/rise azimuths if not
  already (has `sunset_azimuth_for_day`, `az_to_pixel`).
- `src/sunset_cam/setup_server.py` — possibly a frame-snapshot endpoint for reload-safe
  preview; smart-recommend may reuse `detect_sun_centroid`.

## Testing

- Render assertions for each screen's hooks (method choice, AR line elements, edge
  arrows, action-adjacent Confirm).
- `solstice_math`: solstice/equinox azimuths; `az_to_pixel` placement at a given
  heading (already covered—extend for equinox + rise).
- Visual: screenshot-verified via agent-browser against mock + live.
- Hardware: a full install rep per method once redeployed.

## Rollout

Behavior-preserving where possible; the heading sources + confirm pipeline are
unchanged underneath. Ship the AR backbone first (additive), then restructure the
entry/flow.
