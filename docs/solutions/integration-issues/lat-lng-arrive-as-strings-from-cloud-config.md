---
title: lat/lng arrive as JSON strings from the cloud/config and crash the sun math
date: 2026-06-10
category: docs/solutions/integration-issues
module: pi-firmware-aiming
problem_type: integration_issue
component: tooling
symptoms:
  - "Aiming page returns ERR_CONNECTION_CLOSED on the phone; the server thread dies mid-response"
  - "journalctl shows TypeError: must be real number, not str at math.radians(lat_deg)"
  - "Stack: render_align_page -> _facing_data -> sunset_azimuth_for_day -> math.radians"
root_cause: missing_validation
resolution_type: code_fix
severity: high
tags: [serialization, type-coercion, boundary, json, lat-lng, aiming, tests-vs-integration]
---

# lat/lng arrive as JSON strings from the cloud/config and crash the sun math

## Problem
The aiming server feeds `lat`/`lng` straight into `math.radians()`, but they arrive
as **strings** (`"48.7519"`) from `config.json` and the cloud `/heartbeat` response,
so every aiming page load throws `TypeError: must be real number, not str` and the
HTTP thread dies — the phone just sees the connection close.

## Symptoms
- Phone: `ERR_CONNECTION_CLOSED` loading `http://<pi>:8080/`.
- Journal: `TypeError: must be real number, not str` at `solstice_math.py:65`.

## What Didn't Work
- Assuming the server hadn't started — it was listening on :8080 fine; only the
  per-request render crashed.
- Trusting the unit suite: **89 tests were green** because they pass floats directly
  and never exercise the real `config.json` → server path.

## Solution
Coerce to numbers at the two type boundaries, not just at the crash site:
- `heartbeat.parse_placement` (cloud ingress): `float(v) if v is not None else None`
  so `config.json` stores real numbers.
- `aiming_config.resolve_aiming_params` (config egress / immediate unblock):
  `float(lat)`, `float(lng)`, `float(hfov)`, `int(width)` — the existing config on
  the device already held strings, so the egress coercion is what fixes it *now*.

## Why This Works
The resolver normalized *which source wins* but never the *type*. JSON is a stringy
boundary; numbers there may be quoted. Coercing at ingest keeps stored config clean
and the egress coercion is a safety net for already-bad config.

## Prevention
- Coerce/validate types at every external boundary (JSON config, HTTP payloads),
  not only where a value is finally consumed.
- Add a regression test that drives the **real** stringy path, e.g.
  `resolve_aiming_params(config={"lat": "48.75", ...})` must return `float`.
- Pattern to watch: "all unit tests pass but the integration breaks" — the tests
  fed already-correct types. See [[validate-output-before-optimizing-pipeline]].
