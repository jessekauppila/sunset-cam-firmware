# Cloud-Served HTTPS Setup — Design

> **RESCOPED 2026-06-11** (`2026-06-11-phone-first-onboarding-decision-and-plan.md`):
> the **frame-relay below is dropped.** The default onboarding is **phone-AR using the
> phone's own camera** (no lag, no relay). The cloud layer shrinks to a *lightweight*
> HTTPS page + arc/declination compute + a heading hand-off (record the captured aim as
> the placement). Use occasional snapshots, never a live `multipart` relay, if a remote
> operator needs the Pi's view. The "sensing stays on the device" framing still holds,
> but the *live preview* in the primary flow is the phone's camera, not the Pi's.


Date: 2026-06-10
Repos: `the-sunset-webcam-map` (cloud setup UI + relay) + `sunset-cam-firmware`
(frame push + directive execution). **Cross-repo; depends on the fleet control
plane (`2026-06-10-agent-native-fleet-control-plane-design.md`). Design of record
for the next build — not built in this session.**

## Problem

The phone compass (`DeviceOrientation`) needs a **secure context** (HTTPS). The Pi
serves the setup page over `http://<host>:8080`, which is neither HTTPS nor
localhost, so the compass is blocked. Self-signed certs work but spook installers
and don't scale (per-device certs, iOS mDNS-name quirks). Decision (2026-06-10):
serve the setup UI from the **cloud over real HTTPS** instead.

## Architecture

```
Phone ── https://sunrisesunset.studio/setup/{code} ──► CLOUD (real cert; all browser APIs work)
  ▲  live preview frames (relayed)        │ heading/aim capture (compass/tap/manual)
  │                                        ▼
CLOUD ◄── frame push (setup mode) ── PI ──► pulls a `set-aim` directive (control plane)
                                     │ sensing stays local: camera, IMU, sun auto-track
                                     ▼ applies heading (apply_heading/apply_tap) → reports back
```

- **Setup UI lives in the cloud app** (HTTPS) → compass + every modern API work; no
  cert warnings; the installer **doesn't need the camera's WiFi** (remote install).
- **Sensing stays on the Pi** (it has the camera + IMU). The Pi runs sun auto-track
  locally and **reports the live heading** up; the cloud page renders the AR overlay
  + live preview from relayed frames.
- **Preview relay:** the Pi pushes setup-mode frames to the cloud (extend the existing
  snapshot-upload path; ~1–2 fps is enough for aiming). The cloud page shows them.
- **Aim capture → device:** the cloud page captures the heading (phone compass / tap on
  a relayed frame / manual dial) and sends a `set-aim` **directive** down the control
  plane; the Pi applies it via the heading-source backend already built
  (`apply_heading` / `apply_tap`), confirms, reports the result.

## Interactivity / latency

The heartbeat cadence is too slow for live aiming. During *active setup*, use a
faster channel: short-poll or SSE/WebSocket for (a) frame relay up and (b) directive
delivery down. The control-plane directive queue still records the authoritative
command; setup mode just drains it faster. Auto-track is latency-tolerant (the Pi
senses locally, only the *display* is relayed); tap-on-relayed-frame is the laggy
case (the frame is ~1s old) — prefer auto-track / compass / manual when relayed.

## What moves vs. stays (important sequencing implication)

The UI redesign we started in **firmware `setup_alignment.py`** has two halves:
- **Rendering / flow** (method choice, AR overlay, copy, screens) → **moves to the
  cloud app** (the HTTPS setup page). The work is portable: the AR positioning logic,
  `sunset_arc_azimuths`, the heading-source UX all transfer to the cloud component.
- **Sensing / local logic** (camera, IMU, `detect_sun_centroid`, `HeadingState`,
  `apply_heading`, the confirm→placement pipeline) → **stays on the Pi**, now driven
  by directives instead of local HTTP POSTs.

So the firmware-served page becomes a **local fallback** (works on the camera's WiFi
with no cloud), while the cloud page is primary. **Open decision for the next build:**
how much more setup *UI* to invest in `setup_alignment.py` vs. pivoting the redesign
to the cloud app. Recommendation: keep the firmware page as a lean local fallback
(what exists today is enough), and build the *redesigned* flow in the cloud app.

## Build sequence (next, cross-repo)

1. **Control plane first** (its spec's smallest slice) — the directive channel is the
   spine this rides on.
2. **Frame relay** (Pi → cloud setup-mode frames) + the cloud `/setup/{code}` HTTPS
   page rendering them.
3. **Aim capture → `set-aim` directive → Pi applies** (reuse `apply_heading`).
4. **Migrate the redesigned flow** (method choice + AR overlay) into the cloud page.
5. Faster setup-mode channel (SSE/WebSocket) for live feel.

## Risks / notes

- Don't strand installs when offline: keep the local firmware page as fallback.
- Frame relay adds bandwidth/cost during setup only (bounded, low fps).
- Security: the `set-aim` directive must be authenticated like all directives; the
  {code}→camera mapping must be access-controlled (owner-gated).
- This supersedes the firmware-served setup page as the *primary* surface but does not
  delete it.
