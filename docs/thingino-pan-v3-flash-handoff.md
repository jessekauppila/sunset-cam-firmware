# Handoff: get Thingino onto the Wyze Cam Pan v3 (for an Opus session)

Written 2026-11-08 from a Fable session that did the bench onboarding and the
app/firmware preview work. This task is the firmware-flashing part, split out
because it wants a focused session and careful reading of Thingino's own source.

## Findings & verdict (resolved 2026-11-08, Opus session)

**The Pan v3 is NOT SD-flashable today, and — the deciding point — no restore
path can be _proven_ on the hardware before the first write. Per the guardrail
"always establish the backup/restore path before writing," do not flash the Pan
v3 now.** Run Phase 1 on the plain Cam v3 (reversible, no case opening); leave
the Pan v3 parked until the path matures (or return it within the window).

Why — distinguishing confirmed from inferred:

1. **No SD installer exists.** `wltechblog/thingino-installers` has `wyze-cam-pan-v1`,
   `wyze-cam-pan-v2` and `wyze-cam-3` but **no `wyze-cam-pan-v3`**; no open issue
   there mentions it; no `docs/cameras/` page for it. _(confirmed 2026-11-08)_
2. **Stock SD recovery is reported broken on this exact model.** Wyze-forum
   owners (2023–24) ran `recovery_wyzepan3.bin` on FAT32 and got no flash / a
   hung purple LED, while the same cards recovered a Cam v2 and Cam v3 fine; one
   lone success needed one specific SanDisk 32 GB card. So the `autoupdate-full.bin`
   path the Cam v3 revert leans on is exactly what fails here. A separate report
   has the slot ignoring some SD cards outright. _(owner-reported, multiple
   independent threads — matches the premise for this task)_
3. **No Petcube-style SD auto-exec install hook.** The Petcube installs over SD
   because stock firmware auto-runs `/mnt/mmc01/cubeclient` every boot; no
   evidence the Pan v3 has any equivalent. And open issue **#1911** (2026-11-02):
   the Pan v3 Thingino profile lacked the SD-slot power GPIOs (47, 54, active
   low), so the slot does not even power on under Thingino until that lands.
   _(no positive evidence of an SD install path)_
4. **The USB-boot net is unproven on this model.** Ingenic USB boot (`a108:c309`;
   thingino-dfu / webflash.thingino.com) is the generic recovery, and the
   no-disassembly OTG variant is confirmed for the Pan v2 — but explicitly does
   **not** work on the Cam v3 (same SoC family), and the Pan v3 is listed for
   neither. The Pan v3 USB port may be power-only (data wires soldered to the
   Wi-Fi module's D+/D- pads); entry generally needs the case open and flash
   pins 5&6 shorted. _(by analogy only — no Pan v3 confirmation)_
5. **CH341A in-circuit is not a safe assumption either.** A teardown of another
   T31 camera found in-circuit CH341A reads failed because the programmer
   back-powers the SoC, forcing a flash-chip desolder. So "just clip the SPI
   chip for a backup" may require isolating/desoldering the chip.
   _(cross-model evidence, not Wyze-specific)_
6. **Even a current image booting is inferred.** The T31X secureboop boot fix
   (PR **#1901**, merged 2026-11-07 22:42 UTC) was validated on a Wyze **VDB2,
   not a Pan v3**; the 10-04 campan3 release showed the same corrupted clock
   table it fixes. One person (Discord `livingflore`, per #1911) does run
   Thingino on a Pan v3, but how they flashed it is unstated.

What that leaves for "restore path before any write":
- **Provable beforehand:** entering USB boot (short flash pins 5&6, see
  `a108:c309`), and a full 16 MB dump via thingino-dfu / Web Flasher, verified by
  reading twice and comparing hashes.
- **NOT provable beforehand:** that stock SD recovery works (it doesn't here),
  that an in-circuit CH341A dump works, that a USB-boot _restore_ works on a Pan
  v3 (nobody has shown it), or that a restored signed stock image re-boots under
  eFuse-locked secure boot.
- Honest conclusion: **there is no restore path we can prove on this unit before
  the first write.** Flashing it today is a write-without-net gamble.

If Jesse chooses to try anyway (treat as sacrificial, within the return window),
the least-bad order is: open case → confirm USB-boot entry → full flash dump,
verified → flash a build that includes #1901 → keep the dump as the (unproven)
restore. **Do not rely on stock SD recovery as the net.** Decide with Jesse
before buying a programmer or opening the case.

**Revisit when** a `wyze-cam-pan-v3` folder lands in wltechblog/thingino-installers,
or #1911 lands _and_ someone confirms a post-#1901 image boots + restores on a
Pan v3.

Sources: themactep/thingino-firmware PR #1901, issues #1900 / #1911, the
`USB-Boot-Mode` wiki, `docs/cameras/petcube-c401a.md`; Wyze forum threads 261065
/ 291350 / 332370 / 268875; camdsmith XM68 teardown.

The original task brief follows, kept for context.

## The ask

Jesse owns a **Wyze Cam Pan v3** (bought from Amazon, within the return window)
and wants to run our `thingino/sunset-agent` on it. Unlike the plain Cam v3,
there is **no ready-made SD-card installer** for the Pan v3 yet. Figure out
whether we can flash it safely from the SD slot it has, and if so, produce the
install path and fold it into our tooling (`thingino/prepare-sd`, the README,
the handoff). This is right-to-repair / homebrew firmware on hardware Jesse
owns, using Thingino's documented mechanisms — not an attack on anything.

Jesse is also buying a **plain Wyze Cam v3** as the low-risk Phase-1 camera.
That one already works with `prepare-sd wyze-cam-3` (whole-card image, reversible,
backs up stock firmware). So the Pan v3 is the "why not try it now" experiment:
if it bricks, he returns it. Treat bricking as an acceptable-but-avoidable
outcome and keep a restore path in view at every step.

## What's already confirmed (don't re-derive)

- The camera is a **Wyze Cam Pan v3**, confirmed in the Wyze app ("Wyze Cam Pan
  v3" / "Wyze Pan V3" badge, 2026-11-08). It has pan+tilt motors and an SD slot.
- Thingino **supports** it: profile `wyze_campan3_t31x_gc2053_atbm6031` (and an
  `..._mmc` variant) in `themactep/thingino-firmware/configs/cameras/`. The
  profile maps the status LEDs (so `find-status-led` is unnecessary here) and the
  pan/tilt motors (so this camera could later aim itself at the sunset azimuth,
  like the Sonoff B1P — see `docs/thingino-bringup-handoff.md`).
- This SoC has eFuse-locked secure boot. Thingino boots on it via its
  **`secureboop`** package (`package/thingino-secureboop/`). **Read that package
  and the profile's `_defconfig` directly** — that's the authority on how the
  image is built and why stock images may or may not boot. Don't take my
  paraphrase; read the source.
- There is a **known, recently-fixed boot bug** affecting T31X secureboop images
  (issue #1900 / PR #1901, merged 2026-11-07, for the Wyze VDB2). The PR notes
  it "probably also explains the Pan v3 release images not booting." So: a Pan v3
  image built/released **before ~2026-11-07 may not boot**; a current build or
  release likely does. **Verify the release date of whatever image you use.**

## The central unknown to resolve first

Is there an **SD-card auto-exec path** on the Pan v3's stock firmware — i.e. does
stock Wyze firmware run a known file from the SD card at boot that we can use to
drive the flash, the way the Petcube C401A installer does? Read
`themactep/thingino-firmware/docs/cameras/petcube-c401a.md` as the *pattern* (an
eFuse-locked T31 flashed from the SD slot with no programmer, with a stock-firmware
backup written to the card first). Then determine the Pan v3's actual stock
auto-exec hook (Wyze's own `recovery_wyzepan3.bin` SD path is a lead for the file
layout; the Thingino `thingino-installers` repo and Discord are the other sources).

If an SD path exists → the Pan v3 keeps the "no case opening" property and this is
low-risk. If it doesn't → the fallback is USB/DFU (`thingino-dfu`), which is more
involved and is where bricking risk climbs; decide with Jesse before going there.

## Where to look

- `github.com/themactep/thingino-firmware` — profile defconfig, `secureboop`
  package, `docs/cameras/petcube-c401a.md`, issues/PRs #448/#450/#451 (Pan v3
  GPIOs), #1900/#1901 (the boot fix). Check `docs/cameras/` for a Pan v3 page.
- `github.com/wltechblog/thingino-installers` — has `wyze-cam-3` and
  `sonoff-outdoor-b1p` SD installers; check for a Pan v3 folder or open issues,
  and read `make_installers.sh` for how an installer image is assembled.
- Thingino Discord (`discord.gg/s6yJzhS4hD`) — per the installer README, the real
  place Pan v3 install status is discussed. Ask Jesse to search/ask there; it may
  be the fastest way to learn if an SD installer is in progress.
- Our side: `thingino/prepare-sd` (macOS SD writer, safety-gated), `thingino/sunset-agent`
  (already declares `preview: true`; status LEDs already mapped for this camera),
  `thingino/README.md` test plan, `docs/thingino-bringup-handoff.md`.

## Deliverables

1. A clear verdict: SD-flashable now, SD-flashable once X lands, or USB/DFU-only.
2. If SD-flashable: the exact file layout + steps, a restore-to-stock path, and
   a `prepare-sd` mode (or sibling script) that stages it — matching how the
   Cam v3 path already works, with the same "confirm before writing" safety.
3. Update `docs/thingino-bringup-handoff.md` and the README so the next session
   isn't surprised by the Cam-v3-vs-Pan-v3 difference. (A memory note already
   records that the bench camera is a Pan v3, not a Cam v3.)
4. Keep commits on PR #17's branch (`feat/thingino-agent`) or a stacked branch;
   land small, push the same day.

## Guardrails

- Everything here is on Jesse's own hardware for interoperability/recovery.
- Always establish the stock-firmware **backup/restore path before writing**.
- Prefer the current/newest Thingino image (post-#1901). Verify its date.
- The plain Cam v3 is the safe Phase-1 camera; the Pan v3 is the experiment.
