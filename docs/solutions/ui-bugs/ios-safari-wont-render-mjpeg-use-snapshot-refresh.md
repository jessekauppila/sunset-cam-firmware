---
title: iOS Safari won't render an MJPEG <img> — use snapshot-refresh instead
date: 2026-06-11
category: docs/solutions/ui-bugs
module: pi-firmware-aiming
problem_type: ui_bug
component: frontend_stimulus
severity: high
symptoms:
  - "Live camera preview is blank on iPhone but the server returns the stream fine"
  - "GET /preview.mjpg returns 200 with valid multipart frames, yet <img> shows nothing"
  - "Works on desktop Chrome, blank on iOS Safari"
root_cause: wrong_api
resolution_type: code_fix
tags: [ios, safari, mjpeg, multipart, preview, snapshot, camera, raspberry-pi]
---

# iOS Safari won't render an MJPEG <img> — use snapshot-refresh instead

## Problem
The setup wizard's live preview was a `<img src="/setup/preview.mjpg">` serving
`multipart/x-mixed-replace` (MJPEG). It rendered on desktop but was **blank on iPhone** —
even though the server produced valid frames (`preview.mjpg` → 200, real JPEGs, no
errors). iOS Safari does not reliably display MJPEG multipart streams in an `<img>`.

## Symptoms
- Preview blank on iOS; fine on desktop.
- Server side healthy: `curl /setup/preview.mjpg` → 200, frames flowing.

## What Didn't Work
- Cache-busting / onerror-retry on the MJPEG `<img>` — iOS just shows nothing (and may
  never fire `onerror`); the infinite stream also wedges page reload.

## Solution
Switch to **snapshot-refresh**: serve a single JPEG endpoint and poll it.
- Firmware: `GET /setup/frame.jpg` → one `capture_jpeg()` (camera-locked; 503 if busy).
- Client: replace the MJPEG attach with a timer that re-sets `img.src =
  '/setup/frame.jpg?t=' + Date.now()` every ~600 ms; clear the timer on detach.
```js
function attachStream(img) {
  const url = api.frameUrl(); if (!url) return;
  const tick = () => { if (img.isConnected && !img.closest('[hidden]')) img.src = url + '?t=' + Date.now(); };
  tick(); img._streamTimer = setInterval(tick, 600);
}
function detachStream(img) { clearInterval(img._streamTimer); img._streamTimer = null; img.src = ''; }
```

## Why This Works
Each tick loads a normal single JPEG, which every browser renders. ~1.6 fps is plenty
for aiming, and there's no infinite connection to wedge reloads. Bonus: the same loop
works over relayed snapshot frames in a cloud deployment.

## Prevention
For any device-camera web preview that must work on iPhones, default to
snapshot-refresh, not MJPEG. Keep MJPEG only where high fps genuinely matters and the
client is known-capable.
