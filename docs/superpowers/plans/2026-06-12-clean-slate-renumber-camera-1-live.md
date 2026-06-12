# Clean-Slate Renumber → Camera 1 Live — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Force the bench unit (`sunset-cam-1`, currently `cameras.id=4`) to the single coherent identity **`cameras.id = 1`** (token-preserving), delete the retired first-build camera, give camera 1 a fresh archive, post a live frame, and confirm it shows healthy on web PRs #64/#65.

**Architecture:** One atomic, destructive prod SQL transaction does the cleanup + primary-key move (data is disposable — confirmed). The device keeps its existing token; only `config.json camera_id 4→1` changes. Then re-pair (fresh `webcams` row), post one frame, fix the capture window, smoke-test the map.

**Tech Stack:** Postgres (Neon) via `psql`, prod `DATABASE_URL` from `the-sunset-webcam-map/.env.production.local`; the Pi over SSH (`sunset-cam-1.local`); the cloud snapshot API (`/api/cameras/{id}/snapshot`).

---

## Pre-flight — read before any step

**Who runs what (standing rule):**
- **YOU run** every step that (a) writes to **prod** or (b) uses the **device token**. Those are marked **[YOU — PROD]** / **[YOU — TOKEN]**.
- **The agent runs** read-only prod checks, the SSH config write, and code/file edits. Marked **[AGENT]**.

**Source of this plan:** `docs/superpowers/specs/2026-06-12-new-camera-commissioning-pipeline-design.md`.
This plan covers **only** the renumber + go-live slice (build steps 1–2). The 1:many
deployment evolution and the HTTPS phone-AR layer are **separate follow-on plans**.

**Verified prod facts (2026-06-12):** `id=1` = `pi-zero-2w-tier0-jesse-house` (retired, webcam
26144288). `id=4` = `pi-zero-2w-sunset-cam-1`, webcam **28759753**, **122 snapshots**, token
valid. FKs as listed in the plan header.

**Safety net (strongly recommended):** before the destructive transaction, take a **Neon
branch** (instant, free copy-on-write) so the whole DB is restorable if anything surprises us.
Neon console → Branches → "Create branch" from `production`. This is the rollback for the
irreversible deletes.

---

### Task 1: Pre-flight snapshot + FK confirmation (read-only)

**Files:** none (queries only).

- [ ] **Step 1: [AGENT] Confirm the two rows + webcam ids are exactly as expected**

Run:
```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map
set -a; source .env.production.local; set +a
psql "$DATABASE_URL" -c "SELECT id, hardware_id, webcam_id, status FROM cameras ORDER BY id;"
```
Expected: exactly two rows — `1 | pi-zero-2w-tier0-jesse-house | 26144288 | active` and
`4 | pi-zero-2w-sunset-cam-1 | 28759753 | active`. **If anything differs, STOP** and re-read
state before proceeding (the destructive SQL hard-codes these ids).

- [ ] **Step 2: [AGENT] Check for claim-code rows that reference either camera**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT id, code, consumed_by_camera_id FROM camera_claim_codes WHERE consumed_by_camera_id IN (1,4);"
```
Expected: 0 or more rows. Note the result — Task 2 clears these so the PK move won't trip the
`camera_claim_codes_camera_fk` constraint.

- [ ] **Step 3: [YOU] Take the Neon branch** (safety net). Confirm the branch exists in the
Neon console before continuing.

---

### Task 2: The renumber transaction (destructive, atomic)

**Files:**
- Create: `the-sunset-webcam-map/.superpowers/camera4-bringup/renumber-to-camera-1.sql`

- [ ] **Step 1: [AGENT] Write the transaction file**

Create `the-sunset-webcam-map/.superpowers/camera4-bringup/renumber-to-camera-1.sql`:
```sql
-- Clean-slate renumber: make the bench unit (id=4) become id=1, token-preserving.
-- Deletes the retired jesse-house camera (id=1) and wipes the bench archive.
-- DESTRUCTIVE + IRREVERSIBLE (take a Neon branch first). Atomic: all-or-nothing.
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f renumber-to-camera-1.sql
BEGIN;

-- Guard: assert the expected rows exist, else abort the whole transaction.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM cameras WHERE id=4 AND hardware_id='pi-zero-2w-sunset-cam-1') THEN
    RAISE EXCEPTION 'Bench unit id=4/pi-zero-2w-sunset-cam-1 not found — aborting';
  END IF;
END $$;

-- 1. Delete retired jesse-house (id=1). Clear its FKs first.
DELETE FROM webcam_snapshots WHERE webcam_id = 26144288;       -- terminator_webcam_state cascades on webcam delete
UPDATE cameras SET webcam_id = NULL WHERE id = 1;               -- release cameras.webcam_fk
DELETE FROM webcams WHERE id = 26144288;                        -- custom_camera_id pointed at cameras(1); gone now
DELETE FROM camera_claim_codes WHERE consumed_by_camera_id = 1; -- release camera_claim_codes_camera_fk
DELETE FROM cameras WHERE id = 1;                               -- frees id=1

-- 2. Wipe the bench unit's archive + release every FK that references id=4 or its webcam.
DELETE FROM webcam_snapshots WHERE webcam_id = 28759753;        -- the 122 frames
UPDATE cameras SET webcam_id = NULL WHERE id = 4;               -- release cameras.webcam_fk
DELETE FROM webcams WHERE id = 28759753;                        -- terminator cascades
UPDATE camera_claim_codes SET consumed_by_camera_id = NULL WHERE consumed_by_camera_id = 4;

-- 3. Move the row to id=1 (device_token_hash + hardware_id + all columns ride along).
UPDATE cameras SET id = 1 WHERE id = 4;

-- 4. Reset the sequence so the NEXT camera is 2.
SELECT setval('cameras_id_seq', 1, true);

COMMIT;

-- verify (read-only, after commit):
SELECT id, hardware_id, (device_token_hash IS NOT NULL) AS has_token, webcam_id, status
FROM cameras ORDER BY id;
```

- [ ] **Step 2: [YOU — PROD] Run it**

Run:
```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map
set -a; source .env.production.local; set +a
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f .superpowers/camera4-bringup/renumber-to-camera-1.sql
```
Expected: `BEGIN … COMMIT`, no errors, and the trailing verify prints **one row**:
`1 | pi-zero-2w-sunset-cam-1 | t | (null) | active`.
If any statement errors, the transaction rolls back (no partial change) — fix and re-run.

---

### Task 3: Verify renumber + token integrity

**Files:** none.

- [ ] **Step 1: [AGENT] Confirm the single clean row + empty sequence state**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT id, hardware_id, webcam_id FROM cameras ORDER BY id;"
psql "$DATABASE_URL" -c "SELECT last_value FROM cameras_id_seq;"
```
Expected: one camera row `1 | pi-zero-2w-sunset-cam-1 | (null)`; sequence `last_value = 1`.

- [ ] **Step 2: [AGENT] Confirm no orphaned children remain**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT count(*) AS snaps FROM webcam_snapshots WHERE webcam_id IN (26144288, 28759753);"
psql "$DATABASE_URL" -c "SELECT count(*) AS webcams FROM webcams WHERE id IN (26144288, 28759753);"
```
Expected: both counts `0`.

---

### Task 4: Point the Pi at camera_id 1 (config, token unchanged)

**Files:**
- Modify (on device): `~/config.json` (or the firmware config path) on `sunset-cam-1.local`

- [ ] **Step 1: [AGENT] Make the config writable, read it back**

Run:
```bash
ssh pi@sunset-cam-1.local 'CFG=$(ls ~/sunset-cam*/config.json ~/config.json 2>/dev/null | head -1); echo "CFG=$CFG"; sudo chmod 666 "$CFG"; python3 -c "import json,sys; p=\"$CFG\"; d=json.load(open(p)); print(\"camera_id=\",d.get(\"camera_id\"),\" token_present=\",bool(d.get(\"device_token\")))"'
```
Expected: prints the config path and `camera_id= 4  token_present= True`. Note the `CFG` path
for the next step.

- [ ] **Step 2: [AGENT] Write camera_id=1 programmatically (NOT nano), preserving everything else, with a round-trip validate**

Run (substitute the `CFG` path printed above):
```bash
ssh pi@sunset-cam-1.local 'CFG=<path-from-step-1>; python3 - "$CFG" <<PY
import json,sys
p=sys.argv[1]; d=json.load(open(p))
d["camera_id"]=1
json.dump(d, open(p,"w"), indent=2)
d2=json.load(open(p))   # round-trip validate
assert d2["camera_id"]==1 and d2.get("device_token"), "validation failed"
print("ok camera_id=",d2["camera_id"]," token_present=",bool(d2.get("device_token")))
PY
sudo chmod 644 "$CFG"'
```
Expected: `ok camera_id= 1  token_present= True`.

- [ ] **Step 3: [AGENT] Restart the service so it picks up the new id**

Run:
```bash
ssh pi@sunset-cam-1.local 'sudo systemctl restart sunset-cam.service sunset-cam-aiming.service 2>/dev/null; sleep 2; systemctl is-active sunset-cam.service'
```
Expected: `active`. (Per the deploy-needs-restart learning — config changes don't take effect
until restart.)

---

### Task 5: Re-pair camera 1 (fresh webcam row + fresh archive)

**Files:**
- Create: `the-sunset-webcam-map/.superpowers/camera4-bringup/pair-camera-1.sql` (adapted from `2-pair-camera4.sql`, id 4→1)

- [ ] **Step 1: [AGENT] Write the pairing file for id=1**

Create `pair-camera-1.sql` — same logic as `2-pair-camera4.sql` but `WHERE c.id = 1`:
```sql
-- Pair camera 1 with a fresh webcams row (token-preserving; idempotent).
BEGIN;
INSERT INTO webcams (source, external_id, title, status, lat, lng, custom_camera_id, last_fetched_at, created_at, updated_at)
SELECT 'custom', c.hardware_id, c.hardware_id, 'active', c.lat, c.lng, c.id, NOW(), NOW(), NOW()
FROM cameras c WHERE c.id = 1
ON CONFLICT (source, external_id) DO UPDATE SET status='active', custom_camera_id=EXCLUDED.custom_camera_id, updated_at=NOW();

UPDATE cameras c SET webcam_id = w.id
FROM webcams w WHERE c.id = 1 AND w.source='custom' AND w.external_id = c.hardware_id;

INSERT INTO terminator_webcam_state (webcam_id, phase, rank, last_seen_at, updated_at, active)
SELECT c.webcam_id, CASE WHEN c.phase_preference IN ('sunrise','sunset') THEN c.phase_preference ELSE 'sunset' END, 0, NOW(), NOW(), true
FROM cameras c WHERE c.id = 1 AND c.webcam_id IS NOT NULL
ON CONFLICT (webcam_id, phase) DO UPDATE SET active=true, rank=0, last_seen_at=NOW(), updated_at=NOW();
COMMIT;
SELECT id AS camera_id, hardware_id, webcam_id FROM cameras WHERE id = 1;
```

- [ ] **Step 2: [YOU — PROD] Run it**

Run:
```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map
set -a; source .env.production.local; set +a
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f .superpowers/camera4-bringup/pair-camera-1.sql
```
Expected: final row shows `camera_id=1` with a **non-null `webcam_id`** (a brand-new id).

---

### Task 6: Post one fresh frame to camera 1

**Files:**
- Use: `the-sunset-webcam-map/.superpowers/camera4-bringup/3-upload-one-frame.sh` with `CAMERA_ID=1`

- [ ] **Step 1: [YOU — TOKEN] Post a frame**

Run (the device token is the one in the Pi's `config.json` — your hands):
```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map
export BASE_URL="https://www.sunrisesunset.studio"
export DEVICE_TOKEN="<camera 1's device token from the Pi config>"
export IMAGE="/path/to/any.jpg"      # any jpg <= 5MB
export CAMERA_ID=1
bash .superpowers/camera4-bringup/3-upload-one-frame.sh
```
Expected: **HTTP 202** with `{"snapshot_id":N,"accepted_at":"..."}`. A 404 means pairing
(Task 5) didn't take — re-check `cameras.webcam_id`.

- [ ] **Step 2: [AGENT] Confirm the frame landed**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT count(*) FROM webcam_snapshots s JOIN cameras c ON c.webcam_id=s.webcam_id WHERE c.id=1;"
```
Expected: `1` (fresh archive, one frame).

---

### Task 7: Fix the capture window so it stays live

**Files:**
- Modify (on device): the same `config.json` (capture-window fields), OR confirm the cloud/cron drives captures.

- [ ] **Step 1: [AGENT] Inspect the current window fields**

Run:
```bash
ssh pi@sunset-cam-1.local 'CFG=<path-from-task-4>; python3 -c "import json;d=json.load(open(\"$CFG\"));print({k:v for k,v in d.items() if \"window\" in k or \"capture\" in k or k in (\"phase\",\"lat\",\"lng\")})"'
```
Expected: prints the `capture_window_*` / `phase` fields. The window was expired (2026-06-07).

- [ ] **Step 2: Decide the source of truth, then set it**

Per the spec's open question: either (a) the device config carries a rolling window, or (b) the
cloud/cron computes the sunset window from `lat/lng`. **If the cloud already computes windows
from `cameras.lat/lng`,** prefer (b) — clear/relax the device window so it captures whenever the
cloud says. **Otherwise** set a current device window programmatically (same chmod 666 → write →
validate → 644 pattern as Task 4, Step 2; never nano). Record which you chose in the spec's
"capture-window source of truth" risk line.

- [ ] **Step 3: [AGENT] Restart + confirm it enters a capturing state**

Run:
```bash
ssh pi@sunset-cam-1.local 'sudo systemctl restart sunset-cam.service; sleep 3; journalctl -u sunset-cam.service -n 20 --no-pager'
```
Expected: logs show the supervisor computing `mode=capture` (or heartbeating with a valid
upcoming window), not a stale/expired-window skip.

---

### Task 8: Smoke-test #64/#65 against live camera 1

**Files:** none (manual verification, signed in as the owner).

- [ ] **Step 1: [YOU] On the My Cameras map (#64), confirm camera 1 shows** a thumbnail and a
health ring (it has a fresh frame; health may read "stale" until it's actually in a sunset
window — that's fine for the render test).

- [ ] **Step 2: [YOU] Click through to `/cameras/1` (#65)** and confirm the detail page renders
the camera with its one image. This is the signed-in smoke test both PRs were waiting on.

- [ ] **Step 3: [AGENT] Record the result** in the coordination doc
`docs/hardware/2026-06-11-board-bringup-and-cross-project-coordination.md` (camera 1 live →
#64/#65 unblocked → parked branches can proceed).

---

### Task 9: Tidy up naming + close the loop

**Files:**
- Rename: `the-sunset-webcam-map/.superpowers/camera4-bringup/` → `camera1-bringup/`
- Modify: the spec's "Tomorrow's first steps" (mark renumber done)

- [ ] **Step 1: [AGENT] Rename the bringup folder + fix internal references**

Run:
```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map/.claude/worktrees/camera-detail/.superpowers
git mv camera4-bringup camera1-bringup 2>/dev/null || mv camera4-bringup camera1-bringup
grep -rl 'camera 4\|camera4\|id = 4\|c.id = 4\|CAMERA_ID:-4' camera1-bringup | xargs -I{} sed -i '' 's/camera4/camera1/g; s/camera 4/camera 1/g' {} 2>/dev/null || true
```
Then [AGENT] read each file to confirm the `1-check`/`2-pair` scripts now describe camera 1 (or
mark them superseded by `renumber-to-camera-1.sql` + `pair-camera-1.sql`).

- [ ] **Step 2: [AGENT] Commit the cloud-repo SQL + rename**

```bash
cd /Users/jessekauppila/GitHub/the-sunset-webcam-map
git add .superpowers/
git commit -m "ops: clean-slate renumber bench unit to camera 1 (SQL + pairing)"
```

- [ ] **Step 3: [AGENT] Mark the renumber done in the spec** and note camera 1 is live.

---

## Self-review notes

- **Spec coverage:** This plan implements build-sequence steps 1 (renumber) and 2 (go-live) of
  the spec. Steps 3 (1:many deployment), 4 (HTTPS phone-AR), 5 (sun-refine) are explicitly
  deferred to follow-on plans — noted in pre-flight.
- **Destructive-prod isolation:** every prod-write and token step is tagged **[YOU]**; the Neon
  branch (Task 1, Step 3) is the rollback for irreversible deletes.
- **Token preservation:** the `UPDATE cameras SET id=1` keeps `device_token_hash` on the row, so
  the device authenticates unchanged after only a `camera_id` config edit (Task 4) — verified by
  the Task 6 frame POST returning 202.
- **No placeholders:** all SQL/ids/commands are concrete from the live schema introspection; the
  only deliberately-open decision is Task 7 Step 2 (window source of truth), which the spec
  flags as a real open question and gives a decision rule for.
