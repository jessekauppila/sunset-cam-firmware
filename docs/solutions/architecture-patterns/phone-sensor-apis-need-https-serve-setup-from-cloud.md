---
title: Phone sensor APIs need HTTPS — serve a device's setup UI from the cloud, not its HTTP
date: 2026-06-10
category: docs/solutions/architecture-patterns
module: pi-firmware-aiming
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - A LAN device (Pi) serves its own setup/config UI over plain HTTP
  - That UI needs a phone browser API gated behind a secure context (compass, camera, geolocation)
  - You want remote / non-technical / at-scale installs
tags: [https, secure-context, deviceorientation, getusermedia, iot, setup, cloud-relay, nat, fleet]
---

# Phone sensor APIs need HTTPS — serve a device's setup UI from the cloud, not its HTTP

## Context
The plan was to capture a heading from the installer's **phone compass**
(`DeviceOrientation`) in the Pi-served setup page. It never worked: the Pi serves
`http://<host>.local:8080`, and browsers expose the compass (and `getUserMedia`,
geolocation, etc.) **only in a secure context** — HTTPS, or `localhost`. A LAN device
on plain HTTP is neither, so the API is silently blocked.

## Guidance
When a device's setup UI needs phone sensor APIs, **don't serve that UI from the device's
HTTP** — serve it from the **cloud over real HTTPS** and relay:
- The setup page lives at `https://yourapp/setup/{code}` (a trusted cert → every browser
  API works; no self-signed cert warnings to scare installers).
- The **device relays its preview frames up** to the cloud (extend the existing
  upload/telemetry path) and **pulls the captured aim down** as a command via your
  device control channel (e.g. heartbeat-delivered directives).
- **Sensing stays on the device** (its camera/IMU); the cloud page is the view + control
  surface. The captured phone-sensor value is computed in the secure cloud page and sent
  down.

Bonus: this **decouples the installer's phone from the device's LAN entirely** —
remote install from anywhere, which is what you want at fleet scale.

Avoid the tempting shortcut of a **self-signed cert on the device**: it works after a
scary "proceed anyway" tap, but it spooks non-technical installers, has iOS mDNS-name
matching quirks, and means a per-device cert to manage across the fleet.

## Why This Matters
The HTTPS/secure-context wall is invisible until a sensor API silently returns nothing.
Discovering it late forces a re-architecture. Knowing it up front turns "phone-compass
setup" from an impossible local-HTTP feature into a clean cloud-served one that *also*
unlocks remote install — a strictly better architecture.

## When to Apply
Any IoT/edge device whose onboarding wants the phone's compass, camera, mic, or
geolocation. Also note the **true-vs-magnetic-north** trap that rides along: phone
compass headings are magnetic; if the device math is true-north, convert
(`true = magnetic + declination`) in the cloud where lat/lng is known.

## Examples
- Blocked: `http://cam.local:8080` → `DeviceOrientation` events never fire on iOS.
- Works: `https://app/setup/{code}` reads the compass, posts the heading down as a
  `set-aim` directive; the device applies it via its existing heading pipeline.
- Local fallback retained: keep a lean device-served HTTP page (manual entry + on-device
  sun detection) for offline installs — just don't put the phone-sensor methods there.
