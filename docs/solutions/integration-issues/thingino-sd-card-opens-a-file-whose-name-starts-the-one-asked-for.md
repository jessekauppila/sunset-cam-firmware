---
title: On a Thingino camera, a name on the SD card can open a different file whose name is the start of it
date: 2026-11-10
category: docs/solutions/integration-issues
module: thingino-setup-card
problem_type: integration_issue
component: tooling
symptoms:
  - "install.sh copied the agent script to /etc/sunset-agent.conf and then deleted the agent from the card"
  - "[ -f /mnt/mmcblk0p1/sunset/sunset-agent.conf ] is true when the file is not on the card"
  - "cat sunset-agent.conf prints the contents of sunset-agent, even when a real sunset-agent.conf exists"
  - "install.sh: line 78: cmp: not found"
root_cause: platform_quirk
resolution_type: code_fix
severity: high
tags: [thingino, fat32, exfat, sd-card, filenames, busybox, tests-vs-device, setup-card]
---

# On a Thingino camera, a name on the SD card can open a different file whose name is the start of it

## Problem
Scripts that run on the camera and read the SD card got the wrong file. With
`sunset-agent` and `sunset-agent.conf` side by side in `sunset/`, the camera
opened `sunset-agent` for both names. The first Cam v3 installed the agent
script as its own config and removed the agent from the card.

## Symptoms
- `[ -f ]`, `cat`, `cp`, `rm` on `<card>/sunset/sunset-agent.conf` all act on
  `sunset-agent`.
- Writing to the longer name writes into the shorter file; `rm` of the longer
  name deletes the shorter file.
- A Mac reads the same card correctly, so nothing looks wrong until the
  camera runs.

## What was measured
On a Wyze Cam v3, Thingino 2026-11-05 (kernel 3.10.14). The card is FAT32 but
mounts as `type exfat`.

- A lookup matches when a **stored name is the start of the name asked for**.
  With `sunset-agent` present: `sunset-agent.conf`, `sunset-agent.conf.example`,
  `sunset-agent.x` and `sunset-agentx` all open it. `S99sunset-agent.bak` opens
  `S99sunset-agent`.
- It happens **even when the longer file really exists**: with all three of
  `sunset-agent`, `sunset-agent.conf`, `sunset-agent.conf.example` on the
  card, `sunset-agent.conf` read back the agent. (`sunset-agent.conf.example`
  read correctly in that layout; don't rely on which.)
- Short names that fit the old 8.3 pattern and were created on the camera
  (`agent` / `agent.conf`, `uenv.txt` / `uenv.txt.tmp`) did not show it. Cards
  are written on a Mac, so don't rely on that either.
- The folder listing is truthful: `ls -1a DIR | grep -qxF NAME`.
- Thingino's own `runonce.sh` / `runonce.done` are safe: neither starts the
  other.

## What Didn't Work
- "Check the listing before `[ -f ]`" (the first fix): it only covers a missing
  file. An existing `sunset-agent.conf` still reads as `sunset-agent`.
- Trusting the tests: they ran on a Mac filesystem, which has no such
  behaviour. The same run hid a second problem, a call to `cmp`, which
  Thingino's busybox doesn't have.

## Solution
Don't put two names on the card where one starts the other.

- The card's `sunset/` folder uses its own short names (`agent.sh`, `initd.sh`,
  `findled.sh`, `camera.conf`, `example.conf`, `rootpass.txt`, `stamp.txt`,
  `install.sh`); `thingino/card-install.sh` installs them under their real
  names on the camera. The table is in `thingino/README.md`.
- On the camera, test for a card file with the listing (`on_card` in
  `card-install.sh`), never `[ -f ]`.
- Never create a work file on the card next to the file it is derived from
  (`uenv.txt.tmp` would be `uenv.txt`). Use the camera's `/tmp`.
- `prepare-sd` removes a stale `sunset/` before staging, so a reused card
  can't keep files under the old names.

## Prevention
- `tests/test_card_install.py::test_no_card_file_name_is_the_start_of_another`
  and `tests/test_prepare_sd.py::test_no_name_on_the_card_is_the_start_of_another`
  fail if a new card file breaks the rule.
- `tests/test_card_install.py` runs the script with only the commands seen on
  the camera on its `PATH`, so the next missing command fails on the Mac.
- For anything new that runs on the camera: run it once on a camera, against
  a scratch folder on its card with `SUNSET_ROOT` pointing at a temporary
  root, before believing the tests.
