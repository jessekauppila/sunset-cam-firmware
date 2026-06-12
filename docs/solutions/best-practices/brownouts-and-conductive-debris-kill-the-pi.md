---
title: Brownouts and conductive debris kill the Pi — power discipline for field devices
date: 2026-06-10
category: docs/solutions/best-practices
module: pi-firmware-hardware
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - Powering a Pi Zero 2 W (or similar) that draws current spikes during work (camera capture, ML)
  - Physically assembling/servicing a board while it is powered
  - Designing a field device that must survive unattended power loss
tags: [raspberry-pi, power, brownout, sd-corruption, hardware-handling, field-device, read-only-root]
---

# Brownouts and conductive debris kill the Pi — power discipline for field devices

## Context
cam1 (Pi Zero 2 W) browned out **during a sunset capture** on a weak supply/cable, then
a **brass standoff was dropped onto the powered board**. End state: power reached the
board (the MPU6050's LED lit on a known-good brick) but the Pi never booted — a dead
SoC. No burn marks. The SD card, camera, and MPU survived. Two separate power mistakes,
one dead board, hours of debugging.

## Guidance
- **Size the supply for the *peak*, not the idle.** A Pi Zero 2 W pulls current spikes
  under load (capture, WiFi TX); a thin cable or a <2.5A brick browns it out. Use a
  solid **5V 2.5A+ supply and a thick cable**. Brownouts both crash the device and risk
  corrupting the SD mid-write.
- **Never handle conductive hardware (standoffs, screwdrivers, jumpers) over a *powered*
  board.** Power down first. A dropped conductive part can short rails and kill the SoC
  with no burn marks to show for it.
- **Make the SD power-loss-proof.** A hard brownout during a write corrupts the
  filesystem and bricks boot. Run a **read-only root** (overlayfs) so power can be cut
  at any instant safely — this is the single highest-leverage resilience change for an
  unattended field device. (Firmware PR #6.)
- **Diagnose power-vs-board fast:** a peripheral's power LED (MPU) lighting while the
  Pi's green ACT LED stays dark = power reaches the board but the SoC won't boot →
  SD or dead board, not the supply. Green ACT dark with everything off = power path.

## Why This Matters
The board death cost an evening and a $15 board, and the *only* reason it wasn't worse
is that the SD/camera/MPU survived (transplantable). At fleet scale, brownout-induced SD
corruption is a silent, recurring field-failure mode you can't fix remotely — design it
out (read-only root + proper power) rather than chasing it per device.

## When to Apply
Every Pi-class field device, especially battery/solar or marginal-power installs, and
any hands-on assembly/servicing.

## Examples
- Bad: capture-time brownout on a phone-charger cable → crash mid-write → unbootable SD.
- Good: 5V/3A supply + read-only root → pull the plug any time, it boots clean next time.
- Recovery when a board dies: transplant **SD + camera + MPU** to a new **Pi Zero 2 W
  *WH*** (pre-soldered header → no soldering); back up `config.json` (device_token,
  lat/lng) off the SD first; reflash only if the SD won't boot.
