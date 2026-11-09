# Handoff: get Thingino onto the Wyze Cam Pan v3 (for an Opus session)

Written 2026-11-08 from a Fable session that did the bench onboarding and the
app/firmware preview work. This task is the firmware-flashing part, split out
because it wants a focused session and careful reading of Thingino's own source.

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
