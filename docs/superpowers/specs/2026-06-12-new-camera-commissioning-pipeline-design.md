# New-Camera Commissioning Pipeline — Design

Date: 2026-06-12
Repos: `the-sunset-webcam-map` (cloud DB + setup page + map) and
`sunset-cam-firmware` (config split, frame push, directive execution).
**Cross-repo design-of-record. Brainstormed in the firmware worktree; executed in a
cloud-repo worktree.**

Supersedes/extends:
- `2026-06-10-cloud-served-https-setup-design.md` (relay already dropped)
- `2026-06-11-phone-first-onboarding-decision-and-plan.md` (phone-AR primary)

It folds those into a single arc: **a camera's journey from unboxing to live-on-the-map.**

## Problem

A freshly-flashed camera has to travel from your bench to a final location (often
someone else's), and become a correctly-placed, visible webcam feed. Today that path is
broken in several places at once:

- **Identity vs. placement are tangled.** `config.json` mixes immutable identity
  (`device_token`, `camera_id`, `api_base`) with field-mutable placement (`lat`, `lng`,
  `lens`, mount ref, window). The cloud has no clean split either.
- **A camera moves.** It's bench-tested at the wrong location, then commissioned at its
  real one — possibly more than once. Images from two locations are *different feeds* and
  must never blend.
- **Pairing is incomplete (B).** Registration leaves `cameras.webcam_id` null, so the
  snapshot endpoint 404s and the camera never surfaces on the map (web PRs #64/#65).
- **A new camera looks dead (C).** Even once visible, it shows nothing until its first
  capture window, instead of a frame at commissioning time.
- **Phone-AR needs HTTPS (A).** The phone's camera + compass APIs require a secure
  context; the Pi serves plain HTTP, so the best onboarding path can't run.
- **Numbering is already off.** This bench unit is hostname `sunset-cam-1` but
  `camera_id 4` in the cloud — drifted from the start.

## Core data model (both repos)

Two entities, cleanly split. This is the spine.

### `Camera` — identity. Created once.
- `id` (the shared **Pi number** — see reconciliation below), `device_token` (secret,
  baked at flash), `name`/`hostname` (e.g. `sunset-cam-1`), owner (always you), `api_base`.
- **Never carries location. Never hand-edited.** This is the row the pairing fix targets.

### `Deployment` — placement + image archive. Many per camera.
- `camera_id` (FK), `lat`, `lng`, `heading`, `lens`, capture window, `started_at`,
  `ended_at` (null = active).
- `state`: `testing` (private to you, discardable — the bench) | `deployed` (public,
  owns the real sunset archive).
- `heading_source` + `coarse`: phone/window/manual ⇒ coarse (eligible for sun-refine);
  sun ⇒ precise. Firmware already records these.
- **This is what the map renders. `webcam_id` points here. Images bind here**, never to
  the bare camera — so a feed never mixes two locations.

### Rules
- A camera's **active deployment** = `ended_at IS NULL` (latest wins).
- **New deployment** when a commissioning lands **> ~100 m** from the active one **and**
  the installer confirms "new location." Within ~100 m = **re-aim the active deployment in
  place** (GPS jitter never splits a feed).
- **Bench bringup = deployment #1, `testing`** (your place, never public, discardable).
  **Field install = deployment #2, `deployed`** (the real feed).
- Moving a camera **closes** the old deployment (`ended_at` set, archive frozen) and
  **opens** a new one.

### Mirrored in firmware config
`config.json` splits conceptually into:
- **Identity** — `device_token`, `camera_id`, `api_base`. Flash-time, immutable.
- **Placement** — `lat`, `lng`, `lens`, `mount_roll_ref_deg`, window. Field-settable,
  arrives **without re-flashing**. The device's local placement is a *cache* of its
  active deployment.

## Identity reconciliation (do this first, it's cheapest now)

**Convention:** **Physical Pi N ↔ `camera_id` N ↔ QR label N.** Assigned together at
provisioning so hostname, cloud id, and the printed sticker can never drift again. This
hardens the "provision per-device config, not nano" rule.

**Why now:** nothing is committed yet — `webcam_id` is null, there's no image archive,
the camera isn't live, the `camera*-bringup` scripts are unrun templates. Renumbering
after go-live would orphan an archive; doing it now is free.

**Steps (cloud-repo, tomorrow's first task):**
1. Run `1-check-camera4.sql`; list camera rows 1–3.
2. Only **two** real cameras exist (2 SD cards / 2 Pis brought up): `sunset-cam-1` and
   `sunset-cam-2`. Everything else is an accident → delete/archive.
3. **Renumber the bench unit `camera_id 4 → 1`**: repoint its `device_token` to a clean
   `camera_id 1` row; map `sunset-cam-2` → `camera_id 2`.
4. Device: `config.json` `camera_id: 4 → 1`, written **programmatically** (chmod 666 →
   write JSON from tooling → validate round-trip → chmod 644). Not nano.
5. Rename `camera4-bringup/*` → `camera1-bringup/*` (swap the id). Trivial — unrun.
6. Backfill this unit's bench row as **deployment #1, `testing`**.

## Section 2 — Thin slice: get camera 1 live (B + C, local path)

Tomorrow's morning target. Prove the whole chain with the path that already works on
hardware — no HTTPS page yet.

1. **Schema:** add `Camera`/`Deployment` + migration. Audit + renumber (above). Backfill
   bench as deployment #1 `testing`.
2. **Pairing fix (B):** registration (or the renumber) populates the active deployment's
   `webcam_id` so the snapshot endpoint stops 404-ing. This is the bug behind "registered
   but invisible."
3. **Commissioning frame (C):** when an aim is confirmed (the existing local
   sun-tap/confirm), the camera **posts one frame immediately** to its active deployment —
   live thumbnail on #64 *now*, not dead-until-sunset.
4. **Result:** camera 1 appears on your "My Cameras," health-ringed, real frame → click →
   #65 detail page. Web PRs #64/#65 and the two parked firmware branches unblock.

## Section 3 — Additive HTTPS phone-AR layer (A)

The second, fancier way to create a deployment. Same `Deployment` model; remote
installer; phone's own camera/compass. Does **not** change the data model.

- **Entry = a permanent QR on the case** (Nelko label, printed at provisioning with the
  matching number; human-readable URL alongside as scan fallback). The QR encodes a
  **stable** per-camera URL, e.g. `https://sunrisesunset.studio/setup/cam-1-<code>`.
- **Access = open (prototype default).** The QR is an open front door to a *locked house*:
  it's a pointer, not a credential. The page only ever exposes **safe, bounded actions for
  that one camera** (set its aim/placement). Worst case is a bad location — redoable,
  visible to you, and subject to the >100 m-+-confirm rule. This maximizes
  move/recalibrate/redistribute: the same sticker rides with the hardware; a new host
  scans the *same* QR to commission at their house.
- **The page is the existing wizard** (`web/setup-wizard/`) hosted over **HTTPS** (so
  `getUserMedia` + `DeviceOrientation` work). Serves `arc-azimuths` + `declination` from
  the deployment's lat/lng.
- **Capture:** phone GPS → lat/lng; phone compass + AR swing → coarse heading
  (`source=phone, coarse=true`). Installer confirms.
- **`record-aim` endpoint** writes a new/updated `Deployment`; the **>100 m + confirm**
  rule fires here (re-aim in place vs. new `deployed` deployment with a fresh archive).
- **Sun refines afterward (Phase B):** over the next few sunsets the Pi upgrades
  `source: phone→sun`, `coarse→precise`. Installer never sweats precision.

## Section 4 — Placement flow + reconciliation

Placement reaches **both** the DB and the camera, from either direction:

- **Cloud → device (phone-AR path):** `record-aim` writes the deployment; the camera
  pulls a **`set-placement` directive** on its next heartbeat and updates its local
  placement cache programmatically. (Camera must be online at the site — it must be anyway
  to post sunsets.)
- **Device → cloud (local sun-tap path):** the camera sets placement locally and **reports
  it up** on the next heartbeat; the cloud writes/updates the deployment.
- **Reconciliation:** **latest-timestamp wins**; cloud is system-of-record once the camera
  is online. The same >100 m + confirm rule decides update-in-place vs. new deployment,
  regardless of origin.
- **Lifecycle/visibility:** `testing` is private to you (bench, smoke tests); a deployment
  goes **`deployed` (public)** only on a confirmed real-location field commission.

## Build sequence (Approach 1 — thin slice first)

1. **Identity reconciliation** (audit + renumber to camera 1).
2. **Section 2 thin slice** → camera 1 live via the local path. *Unblocks #64/#65 + parked
   branches.*
3. **Section 3 HTTPS phone-AR layer** (QR → cloud wizard → `record-aim`).
4. **Section 4 sun-refine polish** (Phase B precision; `set-placement` directive round-trip
   reusing the control plane).

## Risks / open questions

- **DB audit is a prerequisite** to renumbering — confirm which existing rows are the real
  pi-2 vs. accidents before deleting.
- **Open-access QR** is a deliberate prototype choice. The gate is server-side, so an
  **armed-for-setup toggle** can be added later *without reprinting labels* if abuse appears.
- **`set-placement` directive** rides the fleet control plane
  (`2026-06-10-agent-native-fleet-control-plane-design.md`) — its auth applies.
- **Camera must be online** at the field site for cloud→device placement to land; offline
  installs fall back to the local sun-tap path (device→cloud on reconnect).
- **Lens vs. latitude:** the field location's latitude may want a different lens than was
  bench-fitted; the deployment carries `lens`, and the firmware already auto-picks from
  latitude — confirm the field deployment re-evaluates it.

## Tomorrow's first steps (cloud repo)

1. `1-check-camera4.sql` + list rows 1–3 → decide deletes.
2. Camera/Deployment schema + migration; renumber bench → camera 1; backfill deployment #1
   `testing`.
3. Pairing fix (B) populate `webcam_id`; commissioning frame (C) on confirm.
4. Smoke-test #64/#65 against the now-live camera 1.
