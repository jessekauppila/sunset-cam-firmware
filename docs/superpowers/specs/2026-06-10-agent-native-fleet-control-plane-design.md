# Agent-Native Fleet Control Plane — Design

Date: 2026-06-10
Repos: `sunset-cam-firmware` (device executor) + `the-sunset-webcam-map` (cloud
directive queue / fleet API). **Cross-repo — not built in the 2026-06-10 firmware
session; this is the design of record for the next focused build.**

## Problem

A massive remote camera network can't be hand-managed by SSHing into each Pi — and
the Pis sit behind home NATs with no inbound SSH. The felt pain: "I'm on my phone,
can't log into the Pi to fix it." We need to operate, update, and recover the fleet
**without per-device SSH**, optimized for **agent-driven automation + self-healing**
(minimal human involvement).

## Principle

Agent-native: anything a human operator could do to a camera, an **agent** can do via
the cloud control plane. Humans get a phone-friendly admin view over the same API.

## Design

### 1. Spine — the heartbeat becomes the control channel

The device already heartbeats outbound to the cloud (`post_heartbeat`, Bearer
device_token). Extend it:
- The heartbeat **response** carries a `directives[]` array (pending commands for that
  device).
- The device **executes** each directive and reports the outcome on the next beat
  (`directive_results[]` in the request body).
- Pull-based ⇒ NAT-proof, no inbound ports, reuses existing auth. Polling cadence is
  the existing heartbeat interval (tunable per fleet-cost; see the cron-cadence cost
  learning).

### 2. Directives (the verbs)

`reaim`, `restart <service>`, `update` (git pull + restart), `set-config <patch>`,
`ship-logs`, `reboot`, `onboard` / `offboard`. Each is idempotent and carries an id
so results correlate. The device executor maps directive → a guarded local action.

**Permissions wrinkle (firmware):** today the Pi has **no NOPASSWD sudo**, so a
service that runs as the device user can't `systemctl restart` / `git pull` on the
root-owned `/opt/sunset-cam`. Resolve with a tightly-scoped `sudoers.d` entry limited
to the exact deploy/restart commands, OR run the executor as a root systemd unit with
a narrow allowlist. (Documented gap from the 2026-06-10 session.)

### 3. Self-healing (autonomous, per device)

Extend the supervisor (already the AIMING↔ACTIVE brain) into a detect-and-recover
loop: dead camera → restart; crash-loop → roll back to last-good commit; aim drifted
(IMU vs tap-time) → re-aim; repeated errors → auto `ship-logs`. Single-device recovery
needs no human and no cloud round-trip.

### 4. Fleet-wide changes — canary then auto-roll

For directives that touch **many** cameras (update, mass config, mass reaim):
1. Agent applies to a small **canary** group.
2. **Health gate**: heartbeat liveness, capture-success rate, error rate over a watch
   window.
3. Green → auto-proceed to the rest of the fleet in waves; not green → **auto-rollback**
   the canary. No human in the loop, bounded blast radius.

### 5. Agent fleet-API + human admin

Cloud endpoints: list devices, read health/state, enqueue directive, watch results,
manage canary rollouts. Expose as an **MCP tool surface** so an agent operates the
fleet directly; a **phone-friendly admin page** renders the same API for Jesse
(one-tap reaim / restart / view logs).

### 6. Break-glass remote access

Each Pi joins a mesh VPN (Tailscale / WireGuard) so that for the rare deep-debug case,
a human *or* an agent can reach a specific device directly — without port-forwarding —
so a camera is never truly unreachable from a phone.

## Smallest valuable slice (build first)

1. **Cloud**: a per-device directive queue table + `GET`(in heartbeat response)/`POST`
   result, and one enqueue path.
2. **Firmware**: heartbeat pulls `directives[]`, a `directive_executor` that handles
   **one** safe verb end-to-end (`ship-logs` — no sudo, low risk) + reports the result.
3. Prove the loop: enqueue `ship-logs` from the cloud → device ships → result visible.

Then add `restart`/`update` (needs the sudoers fix), then self-healing, then canary.

## Affected areas

- Firmware: `heartbeat.py` (parse `directives`, post `directive_results`), new
  `directive_executor.py`, supervisor self-heal hooks.
- Cloud (`the-sunset-webcam-map`): directive queue schema/migration, heartbeat
  endpoint extension, fleet API + admin UI, canary/rollout controller, MCP tools.

## Testing

- Firmware: `parse_directives(body)`, executor dispatch per verb (pure, mocked side
  effects), result reporting. Self-heal decisions unit-tested via injected health.
- Cloud: queue enqueue/dequeue, health-gate logic, canary state machine, auto-rollback.
- Integration: enqueue → heartbeat round-trip → result, on a single dev device.

## Risks

- **Blast radius**: a bad directive across the fleet. Mitigated by canary + health-gate
  + auto-rollback; never fleet-apply without passing canary.
- **Permissions**: sudo story must be solved before `restart`/`update` directives.
- **Cost**: more heartbeat payload / cloud writes — watch the Neon/Upstash cadence
  cost (existing learning).

## Follow-ups

- Signed directives (don't let a compromised cloud brick the fleet).
- Staged firmware images / A-B partitions for safe `update` + instant rollback.
