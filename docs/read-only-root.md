# Read-Only Root (unplug-safe mode)

A shipped sunset-cam can lose power at any instant — recipients pull the plug, and no non-technical person performs a graceful shutdown. To make that safe, the production SD card runs **read-only with a RAM overlay**: the card is never written during normal operation, so a power cut can't corrupt it. **Unplug anytime.** No button, no shutdown ritual.

Spec: `docs/superpowers/specs/2026-06-08-qr-label-and-shippable-unit-hardening-design.md` (cloud repo) §4.2.

## Why this is safe for *this* device

Read-only root only works if nothing important needs to persist to the SD at runtime — and the architecture already ensures that:

- **Captured images upload immediately** (never stored on the card).
- **Mutable config (lat/lng, capture window) comes from the cloud** each boot via the heartbeat; the supervisor's `write_location` write lands in the RAM overlay and is re-fetched after a reboot — self-healing.
- **Identity** (`device_token`, `camera_id`, `api_base`) is written **once at commission** while the FS is still writable, then baked in read-only — it survives power loss permanently.

So the only thing on the card is the read-only firmware + identity; nothing critical lives only in the (volatile) overlay.

## Provisioning order (operator, per unit)

Read-only is enabled **last**, after the unit knows who it is:

1. Flash the SD image, boot, SSH in.
2. Install firmware (`install.sh`), apply the Arducam overlay fix, **commission** (`configure.sh` writes `device_token`/`camera_id`/`api_base` — the FS must be writable here).
3. Verify the unit works (camera + gyro + a capture/upload).
4. **Enable read-only root and reboot:**
   ```bash
   sudo bash /opt/sunset-cam/scripts/overlay.sh on
   sudo reboot
   ```
5. Confirm it's on: `sudo bash /opt/sunset-cam/scripts/overlay.sh status` → `overlay: ON`. Ship it.

(Baking the overlay into the SD-image *template* is an option once the image build is automated; until then, step 4 is the per-unit enable.)

## Updating a deployed unit (the maintenance window)

Read-only means you can't casually `apt upgrade` / `git pull`. To update OS or firmware, open a writable window, then re-lock:

```bash
sudo bash /opt/sunset-cam/scripts/overlay.sh off
sudo reboot
# ... after reboot (SD writable):
cd /opt/sunset-cam && sudo git pull        # firmware update
sudo apt update && sudo apt upgrade -y      # OS update (optional)
# ... then re-lock:
sudo bash /opt/sunset-cam/scripts/overlay.sh on
sudo reboot
```

Doable over SSH today; a future cloud "maintenance mode" directive can orchestrate it remotely (see the spec's control-surface follow-on).

**Note — the sunset-quality ML is cloud-side** (Vercel), so updating "best sunset" models is a cloud deploy with **zero Pi involvement** — read-only root never gets in the way of that.

## Validation: the unplug test

On a unit with overlay ON, confirm it tolerates power loss:

1. While it's running (ideally mid-capture-window), **pull the power** ~10×, replug each time.
2. After each boot, confirm it comes up clean, the firmware starts, and it **re-fetches lat/lng + mode from the cloud** (check `journalctl -u sunset-cam-supervisor` for a heartbeat + mode line).
3. There should be **no `fsck`/corruption errors** in `dmesg` and no degraded state.

## Known costs (accepted)

- **No persistent on-disk logs** across reboots (logs are in the RAM journal). Mitigated by cloud log-shipping (separate slice) — recent journal lines ride the heartbeat to the cloud.
- **Updates require the toggle window** above (not a casual write).
- **Future features must not assume disk persistence** — write to the cloud, not the card.
- The Pi Zero has no RTC, so NTP-on-boot remains a dependency (unchanged by this).

## Scale tripwire

Identity is baked at commission. If, at fleet scale (thousands of cameras), you need to **rotate a `device_token` or re-bind a deployed unit remotely without a maintenance window**, add a tiny **writable config partition** (root stays read-only; only `/opt/sunset-cam/config` is writable). Defer until that operational need is real — it's an additive upgrade, not a rewrite. (Spec §6.)
