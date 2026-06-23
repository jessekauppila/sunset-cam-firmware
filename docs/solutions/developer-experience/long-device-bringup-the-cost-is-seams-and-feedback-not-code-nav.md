---
title: Long device bring-up — the recurring cost is untested seams + a lossy feedback loop, not code navigation
date: 2026-06-16
category: docs/solutions/developer-experience
module: pi-firmware-deployment
problem_type: developer_experience
component: development_workflow
severity: medium
applies_when:
  - Deciding whether to adopt a context/agent tool (codegraph / context-mode / memory layer) for this project
  - A long bench/bring-up session burned hours and you're tempted to blame "too much context"
  - Retrospective / tooling-investment decisions for the firmware + fleet work
tags: [retrospective, tooling, context-management, integration-test, feedback-loop, memory, codegraph, context-mode, decision]
---

# Long device bring-up — the recurring cost is untested seams + a lossy feedback loop, not code navigation

## Context
After the camera-2 "boots but sits dark" incident (a missing `__main__` guard that took
~3 hours), we audited the whole `docs/solutions/` store (11 findings, all from the
2026-06-10 → 06-16 bring-up sprint) to decide which context tool would help most:
**codegraph** (pre-indexed code structure/callers), **context-mode** (keep bulky tool
output out of the window), or a **memory/persistence layer** (decisions/findings across
sessions + compactions). Caveat on the evidence: it's one ~week-long arc, one operator —
real recurrence, shallow time-base.

## Guidance
**Sort your own findings by what actually burned time before buying a tool.** Here the
clusters were:

- **A. Tests green, the real wired path breaks** — the untested integration/entrypoint
  seam. (`systemd-oneshot-...-main-entrypoint` + its `load_config`/`hardware_id`
  siblings; `lat-lng-arrive-as-strings`: *"89 tests green … never exercise the real
  config.json → server path."*) **The dominant code cost.**
- **B. Testing the wrong thing** — stale or silent process. (`device-config-or-code-
  change-needs-a-service-restart`; a no-op oneshot exits `0`.)
- **C. Lossy device feedback loop** — terminal/paste/SSH mechanics.
  (`agent-drives-the-pi-directly-over-ssh`, `dont-hand-edit-device-json-config`.)

**Striking negative result:** *zero* findings were about re-exploring code / finding
callers / drowning in structure. So:

- **codegraph — skip.** No evidence supports it; failures are at runtime boundaries, not
  in comprehension, and a call graph can't tell you `main()` never *ran*. Would NOT fix
  A, B, or C.
- **context-mode — best for a single long bench session.** Those sessions are a firehose
  of `journalctl`/`systemctl`/`curl`/`pytest`/poll-loops; keeping that out of the window
  drains the saturation that fed the anchoring ("the edge of 1M context" → blind spots).
  But it treats the *symptom* (window pressure), not the cause — you'd still miss the bug
  if you weren't looking at execution.
- **memory/persistence layer — best for the project overall, and the one to adopt going
  forward.** The project is structurally cross-session and compaction-prone and already
  runs *three* overlapping stores (`MEMORY.md` + `docs/solutions/` + `docs/hardware/`
  checkpoints). The proof of leverage: `lat-lng-arrive-as-strings` had *already* recorded
  the exact "tests green, real path breaks" pattern — had it been *recalled and applied*
  when wiring the entrypoints, the class was foreseeable. A consolidated recall path is
  what makes a logged lesson fire at the moment it's relevant.

## Why This Matters
The honest root cause of the incident was **not** a context tool at all: it was (1) a
broken feedback loop to the device — fixed by passwordless SSH putting `journalctl` in
the agent's hands (now extended by `scripts/sunset-cam-deploy.sudoers`) — and (2) a
missing integration test at the entrypoint (now `tests/test_entrypoints_smoke.py`).
A tool purchase that papered over those two would have masked the real fix. Buy tools to
attack your *documented* recurring costs, not the costs a vendor pitch names.

## When to Apply
Any tooling-investment decision for this project; any "we lost hours, was it context?"
retrospective. Re-run the "sort findings by time-cost" pass — the recommendation shifts
as the store grows past this single sprint.

## Examples
- **Most help for the incident:** context-mode (drains the named saturation).
- **Most help going forward:** consolidate the memory layer into one recall path.
- **Don't:** adopt codegraph — the pain is boundaries/runtime/continuity, not navigation.

## Related
- `docs/solutions/integration-issues/systemd-oneshot-python-module-missing-main-entrypoint.md`
- `docs/solutions/integration-issues/lat-lng-arrive-as-strings-from-cloud-config.md`
- `docs/solutions/developer-experience/agent-drives-the-pi-directly-over-ssh.md`
- `docs/solutions/developer-experience/device-config-or-code-change-needs-a-service-restart.md`
