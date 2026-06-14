# Sub-project E — Reconciled Gap Plan (WiFi onboarding + provisioning)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Tests run under **`python3.11`** (default `python3` is 3.9 and fails collection). Baseline: `python3.11 -m pytest -q` → 145 passed.

**Goal:** Build only the GENUINELY-MISSING half of sub-project E — the SETUP / WiFi-onboarding path + provisioning — and *extend* (never rebuild) the already-built ONLINE half, adapting to the shipped deployment model.

**Why this plan exists:** The original E plan (`the-sunset-webcam-map/docs/superpowers/plans/2026-06-13-subproject-E-wifi-onboarding-plan.md`) predates (a) the existing aiming/supervisor firmware and (b) the cloud deployment-model reconciliation. Executed as-written it would DUPLICATE existing modules and build against a stale cloud seam. This gap-plan supersedes it for execution.

**Branch:** `feat/wifi-onboarding-E` (off `feat/deploy-aiming-supervisor`, which carries the supervisor/heartbeat/directive code E extends — stacked PR; rebase if that branch merges to main first).

---

## Audit: already built vs missing (verified 2026-06-14)

### Already EXISTS — verify/extend, do NOT rebuild
- `heartbeat.py` — `post_heartbeat` (Bearer device_token), `parse_placement`, `parse_directives`. (orig E Tasks 8b partial)
- `directive_executor.py` — `execute(directive)` + `ship-logs` handler. (orig Task 8e base)
- `supervisor.py` — `decide_mode(placement_status)`, `run_once`, `run_directives`. (orig Task 8)
- `service_control.py` — `SystemctlController.set_mode`. (orig Task 7 control)
- `placement_report.py` — `post_placement` (device→cloud sun-tap). 
- `setup_server.py` — `AimingService` (the on-device AIMING UI — NOT the WiFi captive portal; leave alone).
- `config.py` — full CAPTURE config loader (`load_config`, requires phase/window). `device_config.py` — `write_location` only.

### MISSING — build (this plan)
1. `has_wifi_credentials` + `decide_boot_state` (BOOT→SETUP|ONLINE) — orig Tasks 6/7.
2. Light **identity config** read (claim_code/camera_id/device_token/api_base) — distinct from the full capture config.
3. `post_register` client (adapted: register no longer returns a token — see Seam below) — orig Task 8a.
4. **Extend** `parse_placement` → also azimuth_deg/tilt_deg/coarse/azimuth_source/bracket/phase_preference; placement consumer (sun-refine vs precise) — orig Task 8c.
5. Wire register→heartbeat-poll→placement into the boot/supervisor path — orig Task 8d.
6. **Extend** `directive_executor` with `wipe_wifi` + normalize string directives — orig Task 8e.
7. Captive-portal Flask app: `iwlist` scan parser, `WifiSetupService` (wpa_supplicant write, mocked subprocess), Flask catch-all, SETUP entrypoint — orig Tasks 9–13.
8. Provisioning: `provision-unit.sh` calling the new `/api/cameras/provision`, config.json identity writer, sticker gen — orig Tasks 16–18 (flash step hardware-gated).

### DEFER — hardware-gated (need a Pi; spec only)
- hostapd/dnsmasq/systemd unit (orig Task 14), SD-image build (orig Task 15), the `dd` flash in provision-unit.sh.

---

## Seam adaptations (deployment model)

- **Register returns NO token.** Provisioning bakes `device_token` + `camera_id` into config.json. `post_register` sends `{claim_code, hardware_id, capabilities, firmware_version}` and consumes `{camera_id, placement_status, placement?}` — it does NOT expect/store a token. (Its main value: announce firmware/caps + learn placement_status.) The device authenticates heartbeats with the provisioned `device_token` (Bearer), as `heartbeat.py` already does.
- **Provisioning uses `POST /api/cameras/provision`** (CRON_SECRET) which mints code+token AND creates the camera identity, returning `{camera_id, claim_code, device_token}`. provision-unit.sh writes ALL THREE into config.json (plus `api_base`). (Supersedes orig Tasks 16/16b which used `admin/claim-codes` — code only.)
- **Placement fields live on the deployment**; the heartbeat response already carries them (azimuth_deg/tilt_deg/coarse/azimuth_source/bracket/phase_preference). `parse_placement` extends to read them.
- **Directive shape:** cloud heartbeat emits `directives: ['wipe_wifi']` (array of STRINGS); firmware executor expects dicts `{id,type,payload}`. **Reconciliation:** `parse_directives` normalizes a bare string `s` → `{"id": None, "type": s}` so the existing executor dispatches it. The `wipe_wifi` handler needs no result-reporting.

---

## Slice A — Boot decision (FIRMWARE, no hardware, pure logic)

### Task A1: `has_wifi_credentials`
**Files:** create `src/sunset_cam/boot.py`; test `tests/test_boot.py`.

- [ ] **Step 1 — failing test.** `has_wifi_credentials(path)` returns True when a non-empty wpa_supplicant creds file with a `network={` block exists, False when the file is missing or has no `network={` block.
```python
def test_missing_file_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    assert has_wifi_credentials(str(tmp_path / "nope.conf")) is False

def test_file_with_network_block_is_true(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"
    p.write_text('ctrl_interface=...\nnetwork={\n ssid="x"\n psk="y"\n}\n')
    assert has_wifi_credentials(str(p)) is True

def test_file_without_network_block_is_false(tmp_path):
    from sunset_cam.boot import has_wifi_credentials
    p = tmp_path / "wpa.conf"; p.write_text("ctrl_interface=/run/wpa\n")
    assert has_wifi_credentials(str(p)) is False
```
- [ ] **Step 2 — run fail:** `python3.11 -m pytest tests/test_boot.py -q`
- [ ] **Step 3 — implement:**
```python
"""Boot-time decisions for the SETUP vs ONLINE split."""
from __future__ import annotations
from pathlib import Path

def has_wifi_credentials(wpa_path: str) -> bool:
    p = Path(wpa_path)
    if not p.exists():
        return False
    try:
        return "network={" in p.read_text()
    except OSError:
        return False
```
- [ ] **Step 4 — run pass.** **Step 5 — commit** `feat(boot): has_wifi_credentials presence check`.

### Task A2: `decide_boot_state`
**Files:** modify `src/sunset_cam/boot.py`; `tests/test_boot.py`.

Returns `"setup"` when no WiFi creds (run the captive portal) else `"online"` (creds exist → join home WiFi → register/heartbeat). Pure decision; the supervisor/main acts on it.
- [ ] **Step 1 — failing test:** no creds → `"setup"`; creds present → `"online"`. (Inject `has_wifi_credentials` via a param defaulting to the real one for testability.)
```python
def test_decide_setup_when_no_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: False) == "setup"
def test_decide_online_when_creds():
    from sunset_cam.boot import decide_boot_state
    assert decide_boot_state(wifi_check=lambda: True) == "online"
```
- [ ] **Step 2 fail. Step 3 — implement:**
```python
from typing import Callable
def decide_boot_state(wifi_check: Callable[[], bool]) -> str:
    return "online" if wifi_check() else "setup"
```
- [ ] **Step 4 pass. Step 5 commit** `feat(boot): decide_boot_state SETUP vs ONLINE`.

---

## Slice B — Register client + placement consumer (FIRMWARE, no hardware)

### Task B1: `post_register` (no-token semantics)
**Files:** create `src/sunset_cam/register.py`; test `tests/test_register.py`. Mirror `heartbeat.py`'s injected-poster style.

POSTs `{claim_code, hardware_id, capabilities, firmware_version}` to `{api_base}/api/cameras/register`; returns the parsed `{camera_id, placement_status, placement}` (placement present only when status='ready'). Does NOT read/store a token (provisioning supplied it). Raises on HTTP error.
- [ ] **Step 1 — failing test** (inject a fake poster returning a response object with `.json()`/`.raise_for_status()`): asserts the URL, the body keys, and that the parsed result carries `camera_id` + `placement_status`; no `device_token` is read.
- [ ] **Step 2 fail. Step 3 implement** (mirror `post_heartbeat`: build url/headers, `poster(url, json=body, timeout=...)`, `raise_for_status`, return parsed). **Step 4 pass. Step 5 commit** `feat(register): device register client (no token, deployment seam)`.

### Task B2: extend `parse_placement` + placement consumer
**Files:** modify `src/sunset_cam/heartbeat.py`; create `src/sunset_cam/placement_consume.py`; tests.

- [ ] Extend `parse_placement` to also extract from `body["placement"]` (when present) `azimuth_deg, tilt_deg, coarse, azimuth_source, bracket, phase_preference` (None when absent). Keep existing lat/lng/placement_status. Update `tests/test_heartbeat.py`.
- [ ] `placement_consume.decide_placement(parsed) -> PlacementDecision` with verbs: `AWAIT` (status != ready), `SUN_SELF_REFINE` (ready AND coarse is True — bracket/coarse aim, run on-device sun refine), `LEGACY_PRECISE` (ready AND coarse not True — precise aim, no refine). TDD.
- [ ] Commit `feat(placement): extend parse + sun-refine vs precise decision`.

### Task B3: wire register→heartbeat→placement into the online path
**Files:** modify `src/sunset_cam/supervisor.py` (and/or a small `online.py`); tests.

A `run_online_rendezvous(...)` (pure-ish, injected register/heartbeat/sleep) that: calls register on entering ONLINE; if not ready, polls heartbeat until placement ready (IDLE); on ready applies `decide_placement` → returns the PlacementDecision the supervisor acts on (`set_mode("capture")` for ACTIVE; enable sun-refine for SUN_SELF_REFINE). Reuse existing `decide_mode`/`run_once` where possible. TDD with injected fakes (no real network/sleep). Commit `feat(online): register→heartbeat→placement rendezvous`.

---

## Slice C — wipe_wifi directive (FIRMWARE, no hardware)

### Task C1: normalize string directives + `wipe_wifi` handler
**Files:** modify `src/sunset_cam/heartbeat.py` (`parse_directives`), `src/sunset_cam/directive_executor.py`; tests.
- [ ] `parse_directives`: normalize each item — a bare `str` → `{"id": None, "type": s}`; a dict passes through. Update tests.
- [ ] `directive_executor`: add a `wipe_wifi` handler that deletes/blanks the wpa_supplicant creds file (injected remover so it's testable; idempotent; returns a detail string). Register it in `_HANDLERS`. The device then re-enters SETUP on next boot (decide_boot_state → setup). TDD. Commit `feat(directive): wipe_wifi handler + string-directive normalization`.

---

## Slice D — Captive-portal Flask app (FIRMWARE, no hardware for logic)

Build per the ORIGINAL E plan Tasks 9–13 (the code there is sound and unaffected by the cloud seam) with these notes:
- Task 9: add Flask to requirements (dev/runtime as the orig plan specifies).
- Task 10: `iwlist` scan parser (pure; test against captured fixture output).
- Task 11: `WifiSetupService` — write wpa_supplicant creds + trigger join (mocked subprocess).
- Task 12: Flask app + captive catch-all routes (scan list → submit creds → write → reboot/online).
- Task 13: SETUP entrypoint `scripts/run-setup-app.py`.
Each TDD, `python3.11 -m pytest`. Commit per task. (No deployment-seam changes here.)

---

## Slice E — hostapd/dnsmasq/systemd + SD image (DEFER — hardware-gated)
Spec from the orig E plan Tasks 14–15 stands; do NOT execute until a Pi is available. Capture nothing new here.

---

## Slice F — Provisioning (FIRMWARE; flash step hardware-gated)

### Task F1: provision config.json identity writer (pure)
**Files:** extend `src/sunset_cam/device_config.py` (or new `provision_config.py`); tests.
- [ ] `write_identity(path, *, claim_code, camera_id, device_token, api_base)` writes the minimal identity config the device boots with (merge-preserving any existing keys, like `write_location` does). TDD. Commit.

### Task F2: provision client + `provision-unit.sh`
**Files:** `scripts/provision-unit.sh` + a small testable python mint client calling `POST /api/cameras/provision`.
- [ ] The mint client POSTs to `{api_base}/api/cameras/provision` with `Bearer $CRON_SECRET` + `{hardware_id, label}`; parses `{camera_id, claim_code, device_token}`. TDD the client (injected poster).
- [ ] `provision-unit.sh`: mint → write identity config.json → generate sticker (Task F3) → (⚠️ hardware-gated) `dd` flash → append CSV log. `DRY_RUN=1` skips the flash so the rest is testable.
- [ ] Commit `feat(provision): provision-unit via /api/cameras/provision + identity config`.

### Task F3: sticker generation (QR + human code)
Per orig E plan Task 17 (QR encodes the stable setup URL `…/setup/<claim_code>`). TDD. Commit.

---

## Execution order & gate
A1→A2 (boot) → B1→B2→B3 (online/register/placement) → C1 (wipe_wifi) → D (captive portal) → F (provisioning). Slice E deferred.
Final gate: `python3.11 -m pytest -q` all green; no duplication of the existing ONLINE modules; the orig E plan's stale tasks (rebuild heartbeat/supervisor/directives; admin/claim-codes provisioning; superseded-migration verification) are NOT executed.

## Self-review
- Covers every MISSING item from the audit; every "already exists" item is verify/extend, not rebuild. ✓
- Seam adaptations (no-token register, provision endpoint, deployment placement fields, string-directive normalization) each map to a task. ✓
- Hardware-gated items explicitly deferred, not silently skipped. ✓

---

## Remaining work + product-lifecycle timing (added 2026-06-14, after hardware validation)

E's core onboarding loop is hardware-validated end-to-end on a spare Pi Zero W (current Pi OS / NetworkManager). Remaining work, ordered by WHERE in the product lifecycle it belongs:

### Stage 0 — Prototype (now) ✅ DONE
Validate the flow by hand (manual `systemctl start sunset-cam-setup`). Proven on hardware.

### Stage 1 — First shippable unit ("a customer can use it unattended")
These are CORRECTNESS requirements, not scale — they come EARLY, before shipping even one unit:
- **Enable the boot dispatcher as a real systemd boot** (`systemctl enable sunset-cam-boot.service`). The device must auto-decide SETUP vs ONLINE at every boot with no SSH. Small (enable + verify auto-decide). This is NOT a scale feature — it's required for any unattended unit.
- **Bad-WiFi-password safety net** — if the join fails after the post-SETUP reboot, fall back to SETUP so a wrong password self-recovers (no lock-out / brick). Required so a typo doesn't strand a customer.
- **Cloud provisioning live** — `/api/cameras/provision` (mint identity+token, create the camera, print sticker) needs PR #67 deployed. Required so each shipped unit gets its real cloud identity.

### Stage 2 — Small batches (more than 1–2 units)
- **Commission script** (user ask) — one script per Pi: install firmware + services + enable the boot dispatcher + provision identity + print sticker. Two layers: (a) Pi-side install (buildable NOW, no cloud) and (b) cloud provisioning (needs PR #67). Build it when hand-setup becomes the bottleneck — i.e. when you commit to a small batch. Before that, by-hand is fine (firmware still changing fast).

### Stage 3 — Scale manufacturing (batches of ~10+)
- **SD-image / flash automation** — build ONE golden SD image (OS + firmware + services + configs pre-baked) so each unit = `dd` the image in minutes, no per-unit install. This is the difference between "install software on each Pi" and "clone a finished disk." It SUPERSEDES the commission script's per-unit install. Worth the effort only when per-unit install is the bottleneck (batches). Not needed for the first few units.

### Production polish (any time after first ship)
- **Captive-portal auto-popup** (DNS hijack) — the portal opens automatically in the OS captive-network assistant; also softens the "not secure" warning.
- Numeric-id auth on decommission/pause endpoints (cloud); firmware parked-branch consolidation.

**Key distinction:** "enable the boot dispatcher as a real systemd boot" (Stage 1, required for ANY unattended unit) is separate from "SD-image/flash automation" (Stage 3, a manufacturing-efficiency optimization). The first is correctness; the second is scale.
