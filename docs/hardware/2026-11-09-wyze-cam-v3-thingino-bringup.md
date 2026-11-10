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
| Reset Wi-Fi | **Hold the reset button 5 s** (chime) → `wlan reset; reboot` → portal returns. (20 s = factory reset; a tap = speaks the IP.) Re-entered with `GL-X3000-ced` (2.4 GHz) and the router-label PSK. Camera on the LAN at `192.168.8.134`. | — |
| Checks | `date -u` right, TLS ok, `jct`/`curl`/`prudyntctl` present, snapshot 95 KB. SoC serial `246783086410657259533030385283198275336` (t31zx), sensor GC2053, Wi-Fi ATBM6031. | — |
| Backup | Copied `WYZE_BACKUP_jmIKMc/` off the card over SSH to `~/Documents/sunset-cam-backups/wyze-cam-v3-5336/` (combined_backup.bin sha256 `0d0709f5…e21ece`), with a README. | — |
| Wi-Fi on the card | The camera wrote its own SSID + derived 64-hex PSK into `/mnt/mmcblk0p1/uenv.txt` (`wlan_ssid=`, `wlan_pass=`; `wlan configure` accepts the hex PSK, so no plaintext anywhere). | — |
| `sysupgrade -f` | Aug-14 → **2026-11-05** build. SSH drops mid-flash (expected; services are killed). First boot after it came up in the portal (SD not ready?), **second boot read `uenv.txt` and joined Wi-Fi with no portal**. Root password back to default `root`/`root`; the SSH key is gone; re-set both. | ~15 min incl. a portal timeout (10 min) |
| Agent install | `install.sh` from the card **ate the agent**: on the camera, a name on the card opens any file whose name is the *start* of it (`sunset-agent.conf` opens `sunset-agent`), so `[ -f ]` was true, the script was copied as the config and then deleted from the card. Fixed by hand over SSH. (Measured properly the next day: see "The card's file names" below.) | ~10 min |
| API host | The agent's default `API_BASE` (apex `sunrisesunset.studio`) answers **307 → www** and curl doesn't follow it; `new-camera` hit the same. Default switched to `www.`. | — |
| Provisioning | `new-camera --no-card` returned 401: production `CRON_SECRET` matched neither local copy and is marked Sensitive in Vercel (unreadable). Rotated it; dashboard Redeploy and `vercel redeploy` were both **Canceled** by the repo's Ignored Build Step (no app change), `vercel deploy --prod` exceeds the 10 MB upload limit. Fix: PR #518 in the map repo (`[deploy]` commit marker); merging it built production with the new secret. | ~45 min |
| Provisioned | `new-camera --no-card --api https://www.sunrisesunset.studio --label wyze-1 --camera-model wyze-v3` → **camera 3 "wyze-1"**, config in `~/.sunset-cam/cameras/3-wyze-1/`. Pushed to the camera over SSH with the template defaults appended. | — |
| **Online** | `register → HTTP 200`, heartbeat `awaiting_location`, `S99sunset-agent` running. `snap` 404 "no paired webcam row" until phone setup completes — expected. Next: open the setup URL at the camera to place and aim it, then watch the first sunset window. | 22:35 |

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
- **Name lookups on the card lie on the camera.** A name opens any file whose
  name is the start of it, even when the longer file exists. No two names on
  the card may be related that way; never `[ -f ]` a path on the card, list
  the folder. See `docs/solutions/integration-issues/thingino-sd-card-opens-a-file-whose-name-starts-the-one-asked-for.md`.
- **API host is `www.`** The apex 307s and busybox curl without `-L` fails
  silently with it. (The Pi uses `requests`, which follows 307s.)
- **Vercel env rotation needs a real commit.** With the repo's ignore-build
  step, Redeploy is a no-op; use `git commit --allow-empty -m "... [deploy]"`
  once map PR #518 is in. Sensitive env vars cannot be read back; rotate.
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
6. **Provisioning depends on a laptop with the right secret.** Tonight's
   401s cost half an hour and a secret rotation. The card flow should carry
   a pre-minted token (setup-card branch does), and the secret should live in
   one place (`.env.local` = production).
7. **No automatic backup custody.** The stock-firmware backup lives on the SD
   card and is lost if the card is reused. The install flow should copy it to
   the cloud, keyed by hardware id.

## Checked afterwards (2026-11-10), for the simpler flow

Read off the live camera (build 2026-11-05) and the app, not assumed:

- **`runonce.sh` works on this build.** `/lib/mdev/automount` runs
  `<card>/runonce.sh` at mount and writes `runonce.done` when it exits 0. The
  FAT lookup quirk does **not** fool its flag check (`runonce.done` tests
  absent next to a `runonce.sh`). So the setup-card auto-install is viable on
  current Thingino; whether the Aug-14 bundled build runs it is still unknown.
- **The installer card is plain files on FAT32:** the boot file
  (`factory_t31_ZMC6tiIDQN`) plus one 16 MB `thingino-<board>.bin` per hardware
  variant (t31x/atbm6031, t31al/atbm6031, t31x/rtl8189ftv); the one it flashes
  ends up as `autoupdate-full.yay`. Swapping in current images should remove
  the `sysupgrade -f` step and the second portal pass. Not yet tried.
- **The portal on this build** has a Scan button, but still asks for a
  hostname and a root password and is Thingino-branded. It is static files in
  `/var/www-portal` (`index.html`, `x/api.cgi`, `x/portal.cgi`): replaceable.
- **No QR decoder and no Bluetooth on the camera** (`zbarimg`, `quirc`,
  `ble-provision`, `hciconfig` all absent). The Wyze-style "show a QR code to
  the lens" pairing would have to be built and cross-compiled.
- **App:** `/setup/<code>` needs no login and already has a "Waiting for your
  camera to connect…" step, but `setup-status` reports `registered` as soon
  as the camera row exists, so it never actually waits for a heartbeat. Every
  camera must be provisioned beforehand with the admin secret; there is no
  self-registration, so a generic downloadable card can't work yet. The Pi
  Wi-Fi onboarding design (sub-project E, `Sunset-Cam-XXXX` hotspot with a
  network dropdown) and its E–F contract already describe the flow a Thingino
  camera should plug into.

## The card's file names, and what changed in the flow (2026-11-10)

Measured on the camera with scratch folders on its card:

- **The lookup problem is worse than first logged.** A stored name that is the
  start of the name asked for wins, *even when the longer file exists*: with
  `sunset-agent`, `sunset-agent.conf` and `sunset-agent.conf.example` all on
  the card, `sunset-agent.conf` read back the agent script. So the setup card
  as designed would have installed the agent as its config on every camera.
  The folder listing is truthful. Names made on the camera that fit 8.3 did
  not show it.
- **No `cmp` on the camera.** `card-install.sh` used it to decide when to
  remove the secrets from the card, so it could never have finished.

What `feat/thingino-setup-card` does about this night's list:

| Problem tonight | Now |
|---|---|
| Old bundled Thingino, `sysupgrade -f`, second portal pass (~15 min) | `prepare-sd` replaces each `thingino-*.bin` on the card with the current release, sha256-checked. Run against the real installer image: the `t31x_gc2053_atbm6031` build it put on the card is byte-identical to the one camera 3 runs after its upgrade. |
| Agent installed by hand over SSH; the card ate the agent | The card installs it (`runonce.sh`), with file names that can't collide. Run on the camera against a scratch card layout: install, start, tidy at the next boot. |
| Wi-Fi typed into the portal; 5 GHz name accepted (~30 min) | `new-camera --wifi-ssid`: asked once on the Mac, carried on the card; a `-5G`/`5GHz` name is refused. |
| Root password back to `root` after the portal is skipped | `new-camera` makes one, keeps it in the camera's folder, the card sets it. |
| `new-camera` and the agent pointed at the apex host (307) | Default is `https://www.sunrisesunset.studio`; a redirect is explained. |
| Verify failed on every card | Fixed in #23 (file-level verify). |

Still open: a whole flash from such a card has not been done (camera 3 is
already flashed; it needs a second Cam v3), and three first-boot behaviours
are unconfirmed. They are listed in `thingino/README.md` under "What has been
tried, and what hasn't". Not addressed here: progress shown on the phone, the
app's waiting screen keying off a heartbeat, backup upload, and provisioning
without the admin secret.
