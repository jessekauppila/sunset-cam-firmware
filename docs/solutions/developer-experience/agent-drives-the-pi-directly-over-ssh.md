---
title: Let the agent drive the Pi directly over SSH instead of dictating copy-paste
date: 2026-06-10
category: docs/solutions/developer-experience
module: pi-firmware-deployment
problem_type: developer_experience
component: development_workflow
severity: medium
applies_when:
  - Debugging/validating firmware on a networked device (Pi) during a session
  - You're tempted to dictate long shell commands for the human to paste into an SSH session
  - The device has passwordless SSH key auth from the dev machine
tags: [ssh, raspberry-pi, workflow, copy-paste, line-wrap, bench-testing, agent-tooling]
---

# Let the agent drive the Pi directly over SSH instead of dictating copy-paste

## Context
Most of a long bench session's failures were not code — they were **copy-paste
mechanics**. Long commands dictated for the user to paste into their Pi SSH session
repeatedly line-wrapped and split into separate commands (`cp a b /etc/...` → the
`/etc/...` ran as its own command; a `curl` lost its URL → "no URL specified"). After
a dropped SSH session, commands silently ran on the **Mac** instead of the Pi
(`sudo` then asked for the Mac password — "it's not liking my password").

## Guidance
When the device has passwordless SSH key auth, **the agent should run non-sudo
commands directly** via the Bash tool: `ssh -o BatchMode=yes pi@host '<cmd>'`.
- `BatchMode=yes` fails fast instead of hanging if a password is unexpectedly needed.
- This eliminated the line-wrap and wrong-machine failure modes entirely — the agent
  drove all the validation (`curl localhost:8080/setup/state.json`, polling loops,
  `systemctl is-active`, reading `journalctl`).
- For **sudo** (root-owned `/opt/sunset-cam`, `systemctl restart`): the Pi has no
  NOPASSWD, so the agent can't sudo non-interactively. Hand the user **one** combined
  `sudo sh -c '...'` so they enter the password once, then the agent takes over the
  read/validate loop.
- Read a root-owned repo as the `pi` user with
  `git config --global --add safe.directory /opt/sunset-cam` (no sudo) to check the
  deployed commit.

## Why This Matters
The terminal/line-wrap gremlins burned more time than any real bug. Direct agent-over-SSH
made the device a first-class, scriptable surface — the same "agent can do anything the
user can" principle, applied to hardware.

## When to Apply
Any session that involves repeatedly running commands on a reachable device with key
auth. Confirm reachability + auth once (`ssh -o BatchMode=yes host 'hostname'`), then
prefer direct calls over dictation. A NOPASSWD sudoers drop-in scoped to the deploy
commands (`scripts/sunset-cam-deploy.sudoers`) closes the last gap — with it installed
the agent owns the full `git pull` + `systemctl restart` + verify loop, not just the
read side.

## Examples
- Verify deploy + health in one call:
  `ssh -o BatchMode=yes pi@cam 'git -C /opt/sunset-cam rev-parse --short HEAD; systemctl is-active sunset-cam-aiming; curl -s localhost:8080/setup/state.json'`
- Live-watch a state machine: a remote `for i in $(seq 1 10); do curl -s .../state.json; sleep 3; done` loop streamed the `tracking` heading updating in real time.
