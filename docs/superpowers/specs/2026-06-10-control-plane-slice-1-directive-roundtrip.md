# Control Plane — Slice 1: Directive Round-Trip (`ship-logs`)

Date: 2026-06-10
Repos: `sunset-cam-firmware` (executor) + `the-sunset-webcam-map` (queue + endpoint).
Parent: `2026-06-10-agent-native-fleet-control-plane-design.md`. This is the
**smallest valuable slice** — prove the loop end-to-end with one safe verb, then
add `restart`/`update`/self-healing/canary on top.

## Goal

Prove: an agent (or admin) **enqueues a directive in the cloud** → the device
**pulls it on its next heartbeat** → **executes** it → **reports the result** on the
following heartbeat → the cloud shows it `done`. One verb only: **`ship-logs`** (no
sudo, low blast radius).

## Data contract

**Directive** (cloud → device, in the heartbeat response):
```json
{ "id": "drv_abc123", "type": "ship-logs",
  "payload": { "unit": "sunset-cam", "lines": 200 } }
```

**Result** (device → cloud, in the next heartbeat request body):
```json
{ "id": "drv_abc123", "status": "done", "detail": "shipped 200 lines",
  "ts": "2026-06-10T20:40:00Z" }
```
`status` ∈ `done | failed`. Unknown `type` → `failed` with `detail`.

## Firmware (`sunset-cam-firmware`)

- `heartbeat.py`:
  - `post_heartbeat(config, results=None)` — include `directive_results: [...]` in the
    request body when results are pending.
  - `parse_directives(body) -> list[dict]` — extract `directives[]` from the response
    (default `[]`). (Sibling to the existing `parse_placement`.)
- `directive_executor.py` (NEW, pure-ish, injectable sinks):
  - `execute(directive, *, log_sink, ...) -> dict` — dispatch by `type`:
    - `ship-logs`: read recent `journalctl -u <unit> -n <lines>` (subprocess; read-only,
      no sudo), `log_sink(camera_id, text)` to a cloud endpoint, return a `done` result.
    - unknown type → `failed`.
  - Idempotency: caller tracks executed ids; never run the same `id` twice.
- Driver loop (extend the **supervisor**'s existing heartbeat tick):
  1. `directives = parse_directives(last_heartbeat_response)`
  2. for each new id → `execute(...)` → collect result
  3. next `post_heartbeat(config, results=collected)`; remember sent ids.
  - Keep cadence = existing heartbeat interval for this slice (no fast channel yet).

## Cloud (`the-sunset-webcam-map`)

- **Migration**: `device_directives` table — `id` (pk, string), `camera_id`,
  `type`, `payload jsonb`, `status` (`pending|sent|done|failed`), `result jsonb`,
  `created_at`, `updated_at`.
- **Heartbeat endpoint** (extend existing `/api/cameras/{id}/heartbeat`):
  - Response: include `directives[]` = rows where `status='pending'` for this camera;
    flip them to `sent`.
  - Request: accept `directive_results[]` → update matching rows to `done|failed` +
    store `result`.
  - Auth unchanged (Bearer `device_token`).
- **Enqueue path** (agent/admin): `POST /api/cameras/{id}/directives {type, payload}` →
  insert `pending`. Owner/agent-gated.
- **Log sink**: `POST /api/cameras/{id}/logs {text}` (Bearer device_token) → store the
  shipped logs (table or blob) viewable in admin. (Or fold logs into the result for v1.)

## Testing

- Firmware: `parse_directives` (present / missing / empty); `execute` dispatch for
  `ship-logs` (mock `log_sink`, mock journal reader) and unknown-type → `failed`;
  idempotency (same id executed once); `post_heartbeat` includes `directive_results`.
- Cloud: enqueue → pending; heartbeat returns it + flips to `sent`; result updates to
  `done`; auth rejects bad token; enqueue is owner-gated.
- Integration (one dev device): enqueue `ship-logs` → next heartbeat delivers it →
  device ships → status `done`, logs visible.

## Acceptance

From the cloud admin (or an agent via the API), enqueue `ship-logs` for a camera; on
the next heartbeat the device ships its recent logs and the directive shows `done` —
**no SSH, no inbound connection.** That proves the spine the fleet-management and
cloud-served-setup specs both build on.

## Out of scope (next slices)

- `restart`/`update` directives — need the `sudoers.d` (NOPASSWD) fix for the deploy
  commands first (documented gap).
- Self-healing (supervisor detect-and-recover), canary-then-auto-roll, signed
  directives, fast setup-mode channel (SSE/WebSocket).
