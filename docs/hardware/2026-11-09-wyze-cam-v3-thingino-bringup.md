# Wyze Cam v3 → Thingino bring-up log — 2026-11-09

First Thingino camera (the plain **Wyze Cam v3**, not the Pan v3). Live log of
the flash and first boot, kept so the next camera — and eventually a product
install — doesn't repeat any of it. Companion to `thingino/README.md`
("First-camera test plan") and `docs/thingino-bringup-handoff.md`.

## Timeline

| Step | What happened | Time |
|---|---|---|
| Card prep | `thingino/prepare-sd --stage-agent wyze-cam-3`, 32 GB card in the MacBook's built-in SD slot. Installer `wyze-cam-3-sd.zip` sha256 `972d2e56…ed572f` (120 MB, Aug 14 build). | — |
| Verify failed ×2 | Write succeeded (120 MB in/out, ~45 MB/s) but the byte-for-byte read-back failed on **two cards**. Diff at byte 1,049,577 = partition start (1,048,576) + 1001 = FAT32 **FSInfo free-cluster count**. macOS auto-mounted the fresh volume and wrote `.fseventsd`/`.Spotlight-V100`, which also touched FSInfo. The cards were fine. | ~5 min lost per card |
| Reader flakiness | The built-in SDXC reader dropped the card after the first write (gone from `diskutil`), and needed 2–3 reseats to come back each time. | ~10 min |
| Manual staging | Script died before `stage_agent`, so `sunset/` was staged by hand (agent, init script, `find-status-led`, conf example, `install.sh`), byte-verified, `._*` sidecars removed with `dot_clean`. | — |
| Flash | Camera unplugged → card in → power. LED **red/blue alternating** = the installer's busy pattern (backup, then flash). | ~3–4 min |
| First boot | Voice prompt **"configuration portal is up"**. Hotspot `THINGINO-xxxx` (password `thingino`). | — |
| Portal | "Initial configuration": hostname `thingino-wyze-cam3-5336`, MAC `02:be:a1:cf:08:1a`, build `wyze_cam3_t31x_gc2053_atbm6031` (2026-08-14). Set root password, **typed the Wi-Fi SSID and password by hand** (no scan list). | — |
| Wrong band | Typed `GL-X3000-ced-5G`. The Cam v3 radio is **2.4 GHz only**; the portal accepted it with no warning. Camera never appeared on the LAN (~15 min of scanning from a Mac that was also on a different subnet — the GL-X3000 travel router — before the cause was found). | ~20 min lost |
| No fallback | Power-cycling did **not** bring the hotspot back. Thingino's `S38wpa_supplicant` only enters portal mode when no SSID/psk is saved; with a wrong SSID it retries forever. | ~10 min |
| Reset Wi-Fi | **Hold the reset button 5 s** (chime) → `wlan reset; reboot` → portal returns. (20 s = factory reset; a tap = speaks the IP.) Re-enter with `GL-X3000-ced` (2.4 GHz) and the router-label PSK. _(in progress)_ | |

## Fixes made during the session

- `thingino/prepare-sd` now verifies the **MBR + every file** against the image
  instead of raw bytes (branch `fix/prepare-sd-verify-unmount`). The raw compare
  can never pass on macOS once the volume auto-mounts.
- `stage_agent` runs `dot_clean` so AppleDouble `._*` files don't ride along.

## Lessons

- **Don't trust a byte-exact verify on macOS.** Any FAT32 volume the OS mounts
  gets written to. Verify the files the camera reads.
- **The built-in SD reader is flaky after a raw write.** If the card vanishes
  from `diskutil`, reseat it; don't rewrite. A USB reader may behave better.
- **LED language (Cam v3 installer):** red/blue(/purple) cycling = working;
  the known failure (installers #72, early-revision boards) is a ~1-minute
  cycle → solid red a few seconds → repeat, forever.
- **Order on first boot:** Wi-Fi portal → `sysupgrade -f` (the bundled image is
  months old and a full upgrade wipes the overlay) → Wi-Fi portal again →
  `sh /mnt/mmcblk0p1/sunset/install.sh`. Installing the agent before the
  upgrade loses it.
- **2.4 GHz only.** The Wyze Cam v3 (and most of these ESP/Ingenic cameras)
  can't see 5 GHz networks. Any `-5G`/`_5GHz` SSID is wrong; the portal won't
  tell you.
- **No wrong-Wi-Fi fallback.** A saved-but-wrong SSID never returns to the
  portal. Hold reset 5 s (one chime) to wipe Wi-Fi and reboot into it.
- **After the portal, tap reset once:** the camera speaks its IP address
  when it's on the network. Saves the router-DHCP-table hunt.
- **Save the backup.** `WYZE_BACKUP_*/combined_backup.bin` on the card is this
  unit's only way back to Wyze. Copy it off the card before reusing the card.

## Product gaps (what a real install must not ask of a user)

Everything below was typed by hand today. For a product, the only thing a
person should enter is a Wi-Fi password (and ideally not even that: the
phone/app already knows the network).

1. **Wi-Fi is typed, not picked.** Thingino's portal on this camera gave a text
   field for the SSID — one typo and the hotspot silently comes back minutes
   later. Today it accepted a 5 GHz network the radio can't join, with no
   warning. A product flow must scan and offer only joinable (2.4 GHz)
   networks, or not ask at all. Two things already exist for this:
   - Thingino reads **`uenv.txt`** on the SD card (`wlan_ssid=`, `wlan_pass=`)
     at boot and skips the portal entirely. `feat/thingino-setup-card`
     (`thingino/card-install.sh`) already writes it. Merge and use it: the
     card carries the Wi-Fi, nobody types an SSID.
   - Current Thingino master pre-scans and shows a network list in the
     portal (`prescan_for_portal`); the Aug-14 installer build predates it. Options: pre-provision Wi-Fi on the SD card at flash time (the
   `feat/thingino-setup-card` branch already heads this way: one command
   provisions the camera in the app and the card installs the agent), or
   provision over the hotspot from our own app page instead of Thingino's.
2. **Two reboots and two portal passes** (old bundled image → `sysupgrade -f`).
   Fix: ship our own installer image with a current Thingino, or run the
   upgrade unattended from the card.
3. **Agent install is a manual SSH step.** Fix: the card runs it on first boot
   (setup-card branch).
4. **Camera identity (`soc -s`) is only known after boot**, so the app-side
   provision happens after the hardware is in hand. Fine for us; for a product
   the card/app flow should register the camera and hand it its token without a
   laptop in the loop.
5. **Progress is invisible.** A user watching a red/blue LED for four minutes
   has no idea whether it's working. The agent should heartbeat "installing /
   installed / online" to the app so the phone shows progress.
6. **No automatic backup custody.** The stock-firmware backup lives on the SD
   card and is lost if the card is reused. The install flow should copy it to
   the cloud, keyed by hardware id.
