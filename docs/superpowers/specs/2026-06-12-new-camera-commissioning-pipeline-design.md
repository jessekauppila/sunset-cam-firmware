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

## Prod state (verified 2026-06-12, read-only check) — READ THIS FIRST

A live `psql` check against prod **disproved three premises** this design was first drafted
on. The truth:

- **Only TWO camera rows exist** (serial gaps at 2,3 are old failed inserts, not rows):
  - `id=1` — `pi-zero-2w-tier0-jesse-house`, paired (webcam 26144288), last seen
    2026-05-17, no heartbeats. The **first build (~a month ago); now retired.**
  - `id=4` — `pi-zero-2w-sunset-cam-1`, the **current bench unit.**
- **The bench unit (id=4) is ALREADY PAIRED** — `webcam_id=28759753`, webcam active.
  → The "pairing fix (B)" is **already done**, not a bug to fix.
- **It has ALREADY POSTED 122 snapshots** (`snapshot_count=122`).
  → The "commissioning frame (C)" gap doesn't exist for this unit; it has an archive.
- It **still heartbeats** (2026-06-11) but **stopped capturing 2026-06-07** — exactly when
  its capture window expired. So it reads **"stale/offline" on the map** despite being
  paired with an archive. The only thing keeping it off #64/#65 as *live* is **no fresh
  frame + expired capture window.**

**Net:** the immediate keystone is tiny (post a fresh frame + fix the window). The real
work is (1) the clean-slate **renumber to a single coherent id**, and (2) the durable
**1:many deployment** evolution + **HTTPS phone-AR** layer for future cameras.

## Core data model (both repos)

Two entities, cleanly split. This is the spine.

### `Camera` — identity. Created once.
- `id` = the **single canonical number, matching the Pi** (`sunset-cam-N` → camera N).
  Also the API/route id (`/api/cameras/N`, `/cameras/N`) and the QR label. One number
  everywhere — no separate display field.
- `hardware_id` (e.g. `sunset-cam-1`), `device_token` (secret, baked at flash), owner
  (always you), `api_base`, `phase_preference`.
- **Never carries location. Never hand-edited.**

### `Deployment` — placement + image archive. Many per camera.
- Evolves the existing `webcams` table (which already carries lat/lng + owns
  `webcam_snapshots`). Today the link is **1:1** (`cameras.webcam_id` ↔
  `webcams.custom_camera_id`); the relocation story needs **1:many**.
- Fields: `camera_id` (FK), `lat`, `lng`, `heading`, `lens`, capture window,
  `started_at`, `ended_at` (null = active).
- `state`: **`testing → deployed → ended`** (the deployment lifecycle).
  - `testing` — private to you, discardable — the bench bringup.
  - `deployed` — public, owns the real sunset archive.
  - `ended` — closed (`ended_at` set, archive frozen/discarded). A deployment reaches
    `ended` when a new placement commit supersedes it, or on decommission.
- `heading_source` + `coarse`: phone/window/manual ⇒ coarse (eligible for sun-refine);
  sun ⇒ precise. Firmware already records these.
- **This is what the map renders. `webcam_id`/the active deployment is what images bind
  to** — never the bare camera — so a feed never mixes two locations.

### Rules
- A camera's **active deployment** = `ended_at IS NULL` (latest wins).
- **A new placement commit auto-ends the prior deployment.** A move **> ~100 m** from
  the active one opens a **NEW deployment** (`testing|deployed`, fresh archive) and
  marks the prior `ended`; a move **≤ ~100 m** **re-aims the active deployment in place**
  (no new deployment — GPS jitter never splits a feed). The installer's "new location"
  confirm gates the >100 m split.
- **Bench bringup = deployment #1, `testing`** (your place, never public, discardable).
  **Field install = deployment #2, `deployed`** (the real feed).
- Moving a camera **closes** the old deployment (`ended_at` set, `state → ended`,
  archive frozen) and **opens** a new one — the same auto-end rule above.

### Pause vs Decommission
- **Decommission** = **end the active deployment** (`ended_at` set, `state → ended`;
  archive frozen/discarded) + an OPTIONAL WiFi-wipe ("clean ship" nicety — a relocated
  unit auto-re-enters SETUP on association failure anyway, so the wipe is optional).
- **Pause** = **stop capture, deployment intact** (still active, `ended_at` null),
  resumable. Unplugging is NOT a decommission — power-off leaves deployment + WiFi
  intact and resumes on power-up. (See the E↔F integration contract §12 for the cloud
  action surface and the device-side `wipe_wifi` directive.)

### Bench-test and recommission, mapped to the lifecycle
- **Bench test** = a `testing` deployment (private, discardable): provision → SETUP →
  operator onboards to operator WiFi → `testing` deployment → verify capture/post →
  **decommission** (end the `testing` deployment + optional WiFi-wipe) → ship clean.
  The same camera then gets a separate `deployed` deployment at the customer site
  (camera : deployment is 1:many; the bench deployment is `ended`, not carried over).
- **Recommission / move** = re-run the wizard via the permanent QR. A move >100 m opens
  a **new** deployment and marks the prior `ended` (fresh archive); ≤100 m re-aims the
  active one. The device keeps its `device_token` across recommission — only the
  deployment/placement changes. (E↔F integration contract §11.)

### Mirrored in firmware config
`config.json` splits conceptually into:
- **Identity** — `device_token`, `camera_id`, `api_base`. Flash-time, immutable.
- **Placement** — `lat`, `lng`, `lens`, `mount_roll_ref_deg`, window. Field-settable,
  arrives **without re-flashing**. The device's local placement is a *cache* of its
  active deployment.

## Identity reconciliation — clean slate to a single id (do this first)

**Goal:** one coherent number per camera, matching the Pi everywhere — serial `id`,
`hardware_id`, API routes, and the QR label all agree. The serial **does** leak (it's in
`/api/cameras/{id}/snapshot` and `/cameras/{id}`), so it must be the right number, not
hidden behind a display field.

**Decision (data is disposable — confirmed):** full clean slate, force the bench unit to
**`id = 1`**, token-preserving.

**Steps (cloud-repo):**
1. **Delete jesse-house** (`id=1`): its `terminator_webcam_state`, `webcam_snapshots`,
   `webcams` row (26144288), then the `cameras` row. Frees `id=1`.
2. **Wipe the bench unit's archive** (`id=4`): its `terminator_webcam_state`,
   `webcam_snapshots` (122), `webcams` row (28759753). Clean start.
3. **Move the row to `id=1`, keeping its `device_token_hash`** (the token rides on the
   row — no re-mint). Either `UPDATE cameras SET id=1 WHERE id=4` after dependents are
   cleared, or capture the hash → delete → re-insert with explicit `id=1`. Enumerate all
   FKs to `cameras.id` first (heartbeats/events/etc.) and clear them — data is disposable.
4. `SELECT setval('cameras_id_seq', 1)` so the next camera is `2`.
5. **Pi config: `camera_id 4 → 1`** only (written programmatically: chmod 666 → write JSON
   from tooling → validate round-trip → chmod 644). **`device_token` unchanged.** Refresh
   `window_id` to drop the `-bench` framing if desired.
6. Re-create deployment #1 (`testing`) for camera 1 via pairing/commissioning → fresh
   archive under `/api/cameras/1`.

**Convention going forward:** provisioning assigns the **same N** to hostname,
`hardware_id` (`sunset-cam-N`), `cameras.id`, and the printed QR label — together — so they
can never drift. Folds into the "provision per-device config, not nano" rule.

## Section 2 — Get camera 1 live (mostly already true)

B (pairing) and C (has frames) are **already satisfied** for this unit. After the renumber,
remaining work to show **live + healthy** on #64/#65:

1. **Post one fresh frame** to camera 1 (`3-upload-one-frame.sh` → `/api/cameras/1/snapshot`
   with the existing device token — **your hands**, it's the one secret step). Lights up a
   current thumbnail.
2. **Fix the capture window** (expired 2026-06-07) — update config, or let the cloud/cron
   drive captures — so it keeps posting in the sunset window instead of going stale again.
3. **Smoke-test #64/#65** signed in: camera 1 health-ringed on the globe → click →
   `/cameras/1` detail. Unblocks the web PRs and the two parked firmware branches.

## Section 3 — Additive HTTPS phone-AR layer (A)

The second, fancier way to create a deployment. Same `Deployment` model; remote installer;
phone's own camera/compass. Does **not** change the data model.

- **Entry = a permanent QR on the case** (Nelko label, printed at provisioning with the
  matching number; human-readable URL alongside as scan fallback). The QR encodes a
  **stable** per-camera URL, e.g. `https://sunrisesunset.studio/setup/cam-1-<code>`.
- **Access = open (prototype default).** The QR is an open front door to a *locked house*:
  a pointer, not a credential. The page only exposes **safe, bounded actions for that one
  camera** (set its aim/placement). Worst case is a bad location — redoable, visible to you,
  subject to the >100 m-+-confirm rule. Maximizes move/recalibrate/redistribute: the same
  sticker rides with the hardware; a new host scans the *same* QR to commission at their
  house. The gate is server-side, so an **armed-for-setup toggle** can be added later
  **without reprinting labels** if abuse appears.
- **The page is the existing wizard** (`web/setup-wizard/`) hosted over **HTTPS** (so
  `getUserMedia` + `DeviceOrientation` work). Serves `arc-azimuths` + `declination` from
  the deployment's lat/lng.
- **Capture:** phone GPS → lat/lng; phone compass + AR swing → coarse heading
  (`source=phone, coarse=true`). Installer confirms.
- **`record-aim` endpoint** writes a new/updated `Deployment`; the **>100 m + confirm** rule
  fires here.
- **Sun refines afterward (Phase B):** over the next few sunsets the Pi upgrades
  `source: phone→sun`, `coarse→precise`.

## Section 4 — Placement flow + reconciliation

Placement reaches **both** the DB and the camera, from either direction:

- **Cloud → device (phone-AR path):** `record-aim` writes the deployment; the camera pulls
  a **`set-placement` directive** on its next heartbeat and updates its local placement
  cache programmatically. (Camera must be online at the site — it must be anyway to post.)
- **Device → cloud (local sun-tap path):** the camera sets placement locally and **reports
  it up** on the next heartbeat; the cloud writes/updates the deployment.
- **Reconciliation:** **latest-timestamp wins**; cloud is system-of-record once the camera
  is online. Same >100 m + confirm rule decides update-in-place vs. new deployment.
- **Lifecycle/visibility:** `testing` private to you; **`deployed` (public)** only on a
  confirmed real-location field commission.

## Build sequence (Approach 1 — thin slice first)

1. **Clean-slate renumber** to `id=1` (token-preserving) + delete jesse-house.
2. **Section 2** → camera 1 live: fresh frame + capture-window fix. *Unblocks #64/#65 +
   parked branches.* (Small, because pairing + archive already exist.)
3. **1:many `webcams`/deployment evolution** (the real schema work) — supports relocation.
4. **Section 3 HTTPS phone-AR layer** (QR → cloud wizard → `record-aim`).
5. **Section 4 sun-refine polish** (Phase B; `set-placement` directive reuses the control
   plane).

## Risks / open questions

- **PK move on prod:** enumerate every FK to `cameras.id` before the `id 4→1` move; clear
  dependents first (data disposable). Do it in one transaction; verify the device token
  still authenticates (`/api/cameras/1/snapshot` with the unchanged token) before declaring
  done.
- **Capture-window source of truth:** decide whether the device config or the cloud/cron
  owns the window so camera 1 doesn't silently go stale again.
- **1:1 → 1:many** is the substantive schema change; the existing `webcams.custom_camera_id`
  back-pointer assumes one. Plan the migration + how the map picks the *active* deployment.
- **Open-access QR** is a deliberate prototype choice; armed-toggle is deferrable server-side.
- **`set-placement` directive** rides the fleet control plane
  (`2026-06-10-agent-native-fleet-control-plane-design.md`) — its auth applies.

## Tomorrow's first steps (cloud repo) — UPDATED

1. ~~Run `1-check-camera4.sql` + audit rows 1–3~~ **DONE 2026-06-12** (findings above).
2. Clean-slate renumber to `id=1` (delete jesse-house; wipe bench archive; move row keeping
   token; reset sequence) + Pi `config.json camera_id 4→1` programmatically.
3. Post one fresh frame to `/api/cameras/1/snapshot` (your hands) + fix the capture window.
4. Smoke-test #64/#65 against the now-live **camera 1**.
5. Then: 1:many deployment evolution → HTTPS phone-AR layer.
