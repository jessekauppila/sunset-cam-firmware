---
title: Never gate the escape hatch — don't block a provided-value path on an irrelevant measurement
date: 2026-06-11
category: docs/solutions/design-patterns
module: pi-firmware-aiming
problem_type: design_pattern
component: frontend_stimulus
severity: high
applies_when:
  - A setup/config flow has a "just set it manually" fallback
  - A gate (level check, validation) is applied uniformly to all paths
  - One path provides the value directly rather than measuring it
tags: [ux, fallback, escape-hatch, gating, setup, aiming, sensor, anti-pattern]
---

# Never gate the escape hatch — don't block a provided-value path on an irrelevant measurement

## Context
The aiming flow gated **every** method on an on-device level check (the IMU roll within
±15° of the mount reference). On a board whose IMU was mounted flipped (read +90 where
the reference said -90), the gate failed — and it blocked **tap, window, AND manual**.
So the operator had **no way to set the camera up at all**: every method, including the
"just point it west" and "just type the heading" fallbacks, returned "level the camera
first." The escape hatches were gated.

## Guidance
- A gate should only apply to paths where the gated condition actually affects
  correctness. The **level** gate matters for **sun-tap/track** (camera roll changes the
  pixel→azimuth mapping), but **not** for window/manual, where the heading is *provided*,
  not measured from the image — the camera's tilt is irrelevant to it.
- **Always keep at least one un-gated escape hatch** so a misconfigured/miscalibrated
  device can still be set up. If a sensor is wrong, the user must still be able to
  proceed manually.
- Implement the gate as a parameter, not a hardcoded precondition:
  `apply_heading(..., gated=has_supplied_tilt)` — gate only when a tilt reference is
  actually supplied (phone), skip it for window/manual.

## Why This Matters
A uniform gate turned a single wrong sensor into "the product cannot be set up." Gates
exist to protect *accuracy*; they must never become the reason a user is stuck with no
path forward. The escape hatch is the thing you most need when something else is broken —
so it's the last thing that should be gated.

## When to Apply
Any setup/onboarding flow with tiered methods + a manual fallback, especially when a
sensor or measurement feeds a gate. Audit: "if this sensor is wrong/missing, can the user
still finish?" If no, you've gated the escape hatch.

## Examples
- Bad: `apply_heading` gates on IMU level for all sources → flipped IMU blocks window +
  manual → unsetupable.
- Good: sun-tap/track gate on level (the math needs it); window/manual never gate; phone
  gates only on its own supplied tilt. There is always a way through.
