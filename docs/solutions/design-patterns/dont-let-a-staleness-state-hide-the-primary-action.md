---
title: Don't let a staleness/confidence state hide the user's primary action
date: 2026-06-10
category: docs/solutions/design-patterns
module: pi-firmware-aiming
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - A UI latches a value from a one-shot user action, then a sensor/derived signal can mark it stale
  - The 'stale' state hides or disables the button that would commit/refresh the value
  - The user is actively adjusting hardware/inputs during the very window the state guards
tags: [ux, interaction-design, state-machine, sensor-fusion, aiming, anti-pattern]
---

# Don't let a staleness/confidence state hide the user's primary action

## Context
The sun-tap aiming flow latched a compass heading from one tap, then a `suspect`
state fired whenever the housing tilt drifted >3° from tap-time, and `suspect`
**hid the Confirm button**. Mounted, that's fine. But during a *handheld* setup the
camera wobbles constantly, so Confirm flickered and vanished — the operator reported
"I tap the sun and nothing happens," when in fact the tap registered and was then
immediately invalidated.

## Guidance
For UIs where the user adjusts inputs live:
- Prefer a **continuously recomputed** value over **latch-then-nag**. If you can
  re-derive the value each frame (here: re-detect the sun and recompute heading),
  do that — staleness becomes impossible and the action stays available.
- If you must latch, **don't hide the commit action** on a low confidence signal —
  show the action with a warning ("aim may be stale — re-confirm") instead of
  removing it. Hiding the only path forward reads as "broken," not "be careful."
- Make silent rejections loud: a refused action with zero feedback is the worst case.

## Why This Matters
The hidden-Confirm bug cost a long debugging detour and made a working pipeline feel
broken. The fix that actually dissolved it was switching to continuous sun-tracking
(no latch, no nag), which is also the better UX. A confidence state should *inform*
the user, never silently remove their only forward action.

## When to Apply
Any setup/calibration UI driven by live sensors (IMU, compass, camera) where the
operator is physically adjusting the rig while the UI evaluates confidence.

## Examples
- Before: `confirmBtn.hidden = (status !== 'tapped')` → drift → `suspect` → button gone.
- After: `confirmBtn.hidden = !(status === 'tracking' || status === 'tapped')`, and a
  continuous `tracking` state recomputes heading every poll so it rarely goes stale.
