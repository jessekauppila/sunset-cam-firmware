---
title: A device config or code change isn't live until the service restarts — verify it
date: 2026-06-11
category: docs/solutions/developer-experience
module: pi-firmware-deployment
problem_type: developer_experience
component: development_workflow
severity: high
applies_when:
  - You git pull or edit config on a device but the running behavior doesn't change
  - A systemd service reads config/code at startup (most do)
  - Debugging "I deployed the fix but it's still broken"
tags: [systemd, deploy, restart, config, raspberry-pi, stale-process, debugging]
---

# A device config or code change isn't live until the service restarts — verify it

## Context
The single biggest time-sink of a long bench session: change after change appeared to
"not work." Every time, the root cause was the same — **the running systemd service was
still the old process**. `git pull` updated the files on disk, and `config.json` was
edited, but `sunset-cam-aiming` kept serving the old code and the old config (it reads
both only at startup). The level gate, the mount reference, the relaxed window/manual
logic — none of it took effect until a restart, yet we kept re-testing against the
stale process and re-debugging already-fixed bugs.

## Guidance
- After **any** `git pull` or config edit on a device, **restart the service** that uses
  it: `sudo systemctl restart <svc>`. A page reload, a re-`curl`, or re-running the
  wizard does **not** reload a long-running server.
- **Verify the restart actually happened** before debugging further:
  `systemctl show <svc> -p ActiveEnterTimestamp --value` — if the timestamp predates
  your change, the change isn't live. Also confirm the deployed commit:
  `git -C <repo> rev-parse --short HEAD`.
- A `git pull` that prints `Already up to date` (or whose changes you can't see) means
  nothing deployed — check you're in the right dir/branch and that the pull fast-forwarded.

## Why This Matters
Hours went into "still broken" loops that were purely a stale process. The fix-verify
cycle is only valid if you're testing the new process. Confirming the deploy landed
(commit + restart timestamp) before re-testing turns a multi-hour confusion into a
30-second check.

## When to Apply
Every device deploy of code or config behind a long-running service (systemd, a daemon,
a server process). Especially when remote and you can't "see" the process state.

## Examples
- Bad: `sudo git pull` → reload the phone → "still says level the camera" → debug for an
  hour. (The server never restarted.)
- Good: `sudo git pull && sudo systemctl restart sunset-cam-aiming` →
  `systemctl show sunset-cam-aiming -p ActiveEnterTimestamp --value` (now) →
  `git rev-parse --short HEAD` (new commit) → *then* test.
