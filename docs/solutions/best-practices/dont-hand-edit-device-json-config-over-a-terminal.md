---
title: Don't hand-edit device JSON config over a terminal — it corrupts; write it programmatically
date: 2026-06-11
category: docs/solutions/best-practices
module: pi-firmware-deployment
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - Setting a per-device config value (lens, mount reference, lat/lng) on a Pi over SSH
  - Tempted to nano the JSON or paste a multi-line heredoc into the device terminal
tags: [config, json, nano, heredoc, ssh, terminal, paste, provisioning, raspberry-pi]
---

# Don't hand-edit device JSON config over a terminal — it corrupts; write it programmatically

## Context
Setting one field (`lens: "standard"`) on a Pi's `config.json` over SSH went badly three
different ways in a row:
1. **nano** — the edit somehow replaced the *entire* file with a single line
   (`"lens": "standard",`), wiping `device_token`, lat/lng, everything. Invalid JSON →
   the aiming server wouldn't start.
2. **`sudo tee <<'EOF'` heredoc** — the user's terminal **auto-indents pasted lines**, so
   every line (including the closing `EOF`) got 2 leading spaces; bash never saw the
   un-indented `EOF` terminator → the heredoc hung forever at `>`.
3. **Long single-line `python -c`** — risks the same paste/line-wrap mangling.

## Guidance
- **Never hand-edit JSON config on a device, and never paste multi-line blocks into a
  flaky device terminal.** JSON is unforgiving (one bad comma bricks it) and terminal
  paste mangles whitespace/terminators.
- **Best: provision config programmatically**, not by hand:
  - From the dev machine over passwordless SSH, make the file writable
    (`sudo chmod 666 config.json` — one short, wrap-proof command), then **write it from
    your own tooling** (`ssh host 'python3 - <<PY ... json.dump(cfg, open(p,"w")) ... PY'`
    where YOU control the content, no human paste), then restore perms.
  - Better still: deliver per-device config via the cloud control plane (`set-config`
    directive) or bake it at SD-flash time. Installers should never touch a config file.
- **Always round-trip-validate** after writing: `json.load(open(p))` and print a key, so
  you catch corruption before restarting the service.

## Why This Matters
A one-field change destroyed the whole config and cost a recovery cycle, purely because
of hand-editing + terminal paste behavior. The values you'd lose (device_token, lat/lng)
aren't trivially recreatable. Programmatic writes are deterministic and validate-able;
hand edits are neither.

## When to Apply
Any time you'd reach for `nano config.json` or a pasted heredoc on a device. Stop —
write it from tooling with a validation read, or provision it upstream.
