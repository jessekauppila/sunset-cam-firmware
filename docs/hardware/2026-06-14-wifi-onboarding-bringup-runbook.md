# WiFi Onboarding Bring-up Runbook
**Target: bare spare Pi Zero 2 W as camera 2 (camera 1 untouched)**
Date: 2026-06-14

---

## Production TODO — captive-portal auto-popup (DNS hijack)

The setup AP is now **WPA2-protected** (password `sunsetcam`, printed on the device
sticker). The current customer flow is:

1. Find `Sunset-Cam-XXXX` in WiFi settings and join it using the sticker password.
2. When prompted or if no auto-popup appears, open a browser and navigate to
   **`http://10.42.0.1`** manually.
3. The browser may show a "not secure" warning — this is **expected** for a local
   device setup page (no HTTPS on the LAN portal). Proceed past it.

**What is deferred:** the captive-portal **auto-popup** (DNS hijack) that causes
iOS / Android / Windows to automatically open the portal in the OS captive-network
assistant — and which also softens the "not secure" UX by using the OS sheet
instead of a browser. This requires a DNS server that responds to all queries with
`10.42.0.1`, which is not yet wired into `setup-ap.sh`. When implemented, it will
eliminate the "browse to 10.42.0.1" step and the "not secure" browser warning.

**Until then:** the sticker must include the WPA2 password and the `http://10.42.0.1`
address; the portal includes copy explaining the "not secure" warning is expected.

---

This runbook walks through testing the full WiFi-onboarding flow on a bare spare
Pi Zero 2 W provisioned as **camera 2**. Camera 1 is the production unit; it must
not be touched at any point during this procedure.

---

## Hardware you need

- Raspberry Pi Zero 2 W (spare / bench unit)
- MicroSD card (8 GB+)
- SD card reader (USB or built-in)
- Ethernet adapter for the Pi Zero 2 W (USB-C OTG or HAT) — needed only for the
  install step over SSH; WiFi is unavailable until onboarding completes
- A phone (iOS or Android) for the captive-portal test

---

## Known items that need tuning on the Pi

The AP is now brought up via **NetworkManager's native hotspot** (`scripts/setup-ap.sh`
using `nmcli` shared mode). NM handles DHCP and the gateway at `10.42.0.1` automatically
— no separate hostapd or dnsmasq needed.

| Item | Default | Where to change |
|---|---|---|
| wlan0 interface name | `wlan0` | `scripts/setup-ap.sh` (`SETUP_AP_IFACE` env var or edit `IFACE=`) |
| AP IP address | `10.42.0.1` (NM assigns it) | NM shared mode always uses `10.42.0.1`; if you must change it, also update `src/sunset_cam/setup_app.py` catch-all redirect |
| WiFi band | `bg` (2.4 GHz) | `scripts/setup-ap.sh` — change `802-11-wireless.band bg` to `a` for 5 GHz |
| DNS auto-popup (captive sheet) | Not wired yet — manual browse | Browse to `http://10.42.0.1` for now; DNS hijack can be added later |

---

## Step 1 — Flash Raspberry Pi OS Lite

1. Download **Raspberry Pi OS Lite 64-bit** (Bookworm or later) from
   `https://www.raspberrypi.com/software/operating-systems/`.

2. Open **Raspberry Pi Imager**, choose your OS, choose your SD card.

3. In **Advanced settings** (the gear icon):
   - **Hostname:** `sunset-cam-2`
   - **Enable SSH:** yes, with a public key or a password you know
   - **Configure WiFi: LEAVE BLANK** — do NOT pre-configure any home WiFi SSID
     here. If the SD card has WiFi creds in `wpa_supplicant.conf`, the Pi will
     skip SETUP and go straight to ONLINE (boot dispatcher finds creds → starts
     supervisor, not setup). The whole point is to boot credless.
   - Set your locale/timezone if you like.

4. Write the image. Eject the SD card.

---

## Step 2 — Provision camera 2 identity (run from your Mac/workstation)

Before installing firmware you need a `config.json` for camera 2. Run the
provision script from the firmware repo (not from the Pi):

```bash
# One-line — paste as a single command
API_BASE=<prod-api-url> CRON_SECRET=<cron-secret> WEB_BASE=<prod-web-url> \
  ./scripts/provision-unit.sh sunset-cam-2
```

This calls the cloud `/api/cameras/provision` endpoint, mints a camera identity,
and writes `./out/config.json` (and a sticker PNG). Keep the terminal output —
you will need the `camera_id` and `claim_code` for verification later.

> If you are testing against a local dev server, replace `<prod-api-url>` with
> `http://localhost:3000`.

Verify the output: `cat ./out/config.json` should contain at minimum
`camera_id`, `claim_code`, and `device_token`.

---

## Step 3 — Install firmware on the Pi (over ethernet/SSH)

Boot the Pi with the freshly-flashed SD card and an ethernet adapter connected.
Find its IP (check your router's DHCP table or use `arp -a` / `ping sunset-cam-2.local`).

SSH in:
```bash
ssh pi@sunset-cam-2.local
```

Then on the Pi:

```bash
# 3a. Update apt and install system deps
# NetworkManager hotspot mode is used for the AP — no hostapd/dnsmasq needed.
sudo apt update
sudo apt install -y git python3-venv wpasupplicant \
                    python3-picamera2 i2c-tools

# 3b. Confirm NetworkManager is active (Pi OS Bookworm with NM — should be)
sudo systemctl is-active NetworkManager

# 3c. Clone the firmware repo
sudo git clone https://github.com/<your-org>/sunset-cam-firmware /opt/sunset-cam

# 3d. Confirm setup-ap.sh is executable (git should preserve the bit)
sudo chmod +x /opt/sunset-cam/scripts/setup-ap.sh

# 3e. Create venv and install firmware
cd /opt/sunset-cam
sudo python3 -m venv --system-site-packages .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -e .

# 3f. Copy systemd units into place
sudo cp /opt/sunset-cam/systemd/sunset-cam-boot.service \
        /opt/sunset-cam/systemd/sunset-cam-setup.service \
        /opt/sunset-cam/systemd/sunset-cam-supervisor.service \
        /opt/sunset-cam/systemd/sunset-cam.service \
        /opt/sunset-cam/systemd/sunset-cam-aiming.service \
        /etc/systemd/system/

sudo systemctl daemon-reload

# 3g. Enable the always-on services:
#   - sunset-cam-boot (dispatcher, oneshot at boot)
#   - sunset-cam-supervisor (ONLINE path)
#   Leave sunset-cam-setup DISABLED — the dispatcher starts it when needed.
sudo systemctl enable sunset-cam-boot sunset-cam-supervisor

# 3h. Place the provisioned config.json
sudo mkdir -p /opt/sunset-cam/config
# From your Mac (in a separate terminal):
#   scp ./out/config.json pi@sunset-cam-2.local:/tmp/config.json
# Then on the Pi:
sudo cp /tmp/config.json /opt/sunset-cam/config/config.json
sudo chmod 640 /opt/sunset-cam/config/config.json

# 3i. Run firstboot.sh manually for this install (normally run by the service)
sudo bash /opt/sunset-cam/scripts/firstboot.sh

# 3j. Verify /etc/sunset-cam exists with correct permissions
ls -la /etc/sunset-cam/

# 3k. Confirm NO WiFi creds exist (should show nothing after "network={"):
grep -c "network={" /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null && \
  echo "WARNING: creds found — SETUP will be skipped on boot" || \
  echo "OK: no creds, will enter SETUP on boot"
```

---

## Enable unattended boot (Stage 1)

For the device to auto-run the flow at every boot, enable the boot dispatcher.
The dispatcher is a oneshot that starts whichever of the two target services is
appropriate — do NOT enable the setup or supervisor services directly (they are
started on demand by the dispatcher).

```bash
sudo cp /opt/sunset-cam/systemd/sunset-cam-boot.service \
        /opt/sunset-cam/systemd/sunset-cam-setup.service \
        /opt/sunset-cam/systemd/sunset-cam-supervisor.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sunset-cam-boot.service
```

> Note: `sunset-cam-boot.service` declares `After=NetworkManager.service` and
> `Wants=NetworkManager.service` — it will not run until NM is up, ensuring
> `nmcli` can list saved connections and check active ones.

### What happens at each boot

| Creds saved? | Network joins? | Service started | Dispatcher returns |
|---|---|---|---|
| No | n/a | `sunset-cam-setup.service` | `setup` |
| Yes | within ~60 s | `sunset-cam-supervisor.service` | `online` |
| Yes | never (bad password / network down) | `sunset-cam-setup.service` | `setup-fallback` |

**Fallback behavior:** when saved creds exist but NM never completes the join
(wrong password, network unreachable, or DHCP timeout), the dispatcher polls
`is_online()` every 5 s for up to 12 retries (~60 s total). If the join does
not succeed, it falls back to starting `sunset-cam-setup.service` — the setup AP
re-appears and the customer can re-enter or correct their WiFi credentials. This
prevents the device from silently sitting offline forever after a failed join.

To test the fallback: connect the device to a network (creds saved), then change
the WiFi password on your router. Reboot the Pi — after ~1 minute the
`Sunset-Cam-XXXX` setup AP should reappear, allowing credentials to be corrected.

---

## Step 4 — Reboot and watch the boot dispatcher

```bash
sudo reboot
```

Watch the dispatcher oneshot as it runs (SSH back in over ethernet after ~30 s):

```bash
journalctl -u sunset-cam-boot --no-pager
```

Expected output (no creds case):
```
sunset-cam-boot.service: ExecStart succeeded.
systemctl start sunset-cam-setup.service   ← dispatcher chose SETUP
sunset-cam-boot.service: Deactivating
```

Expected output (creds present, join succeeds):
```
sunset-cam-boot.service: ExecStart succeeded.
systemctl start sunset-cam-supervisor.service   ← dispatcher chose ONLINE
sunset-cam-boot.service: Deactivating
```

Expected output (creds present, join fails after ~60 s):
```
sunset-cam-boot.service: ExecStart succeeded.
systemctl start sunset-cam-setup.service   ← dispatcher fell back to SETUP
sunset-cam-boot.service: Deactivating
```

Check that the setup service started:
```bash
systemctl status sunset-cam-setup.service
journalctl -u sunset-cam-setup --no-pager | tail -30
```

Expected: `[setup-ap] up: SSID=Sunset-Cam-XXXX (WPA2, shared, gateway 10.42.0.1)` logged,
then Flask captive portal listening on port 80.

To start the SETUP service manually for testing (survives SSH drop):
```bash
sudo systemctl start sunset-cam-setup.service
```

---

## Step 5 — Phone test (captive portal)

1. On your phone, open WiFi settings.
2. You should see **`Sunset-Cam-XXXX`** (where XXXX is 4 hex chars from the
   Pi's MAC). Connect to it using the **WPA2 password printed on the sticker**
   (default: `sunsetcam`).
3. NM shared mode assigns the Pi gateway `10.42.0.1` automatically.
   **DNS auto-popup is not wired yet** — if iOS/Android does not auto-pop a
   captive-portal sheet, open a browser and navigate to `http://10.42.0.1/`
   manually. Your browser may show a "not secure" warning — this is expected
   for a local device setup page; proceed past it. (DNS hijack can be added later.)
4. Recover from any hang via power-cycle: if creds were already stored, the Pi
   boots straight to ONLINE (supervisor); if not, it re-enters SETUP.
4. The page should show a dropdown of nearby WiFi networks (from `iwlist scan`)
   and a password field.
5. Select your home WiFi network, enter the password, tap Connect.
6. Wait up to 15 seconds. The page should say:
   > "Joined! Reconnect your phone to home WiFi and return to the setup tab."
7. The Pi reboots or continues — the setup service stops, the supervisor starts.

---

## Step 6 — Verify ONLINE path

After the Pi rejoins home WiFi (supervisor starts):

```bash
journalctl -u sunset-cam-supervisor --no-pager -n 50
```

Expected sequence:
- Supervisor registers with the cloud (`/api/cameras/register`)
- Logs: `camera_id=2, placement_status=awaiting_aim` (or similar)
- Heartbeat loop starts

Check cloud side: in the admin panel (or via curl) confirm camera 2 appears with
`setup_status` advancing from `awaiting_wifi` → `registered` → `awaiting_aim`.

---

## Step 7 — Verification checklist

- [ ] Boot dispatcher (`sunset-cam-boot.service`) ran as oneshot and exited 0
- [ ] Dispatcher chose `setup` (journalctl shows `start sunset-cam-setup.service`)
- [ ] AP `Sunset-Cam-XXXX` visible on phone (WPA2-locked)
- [ ] Joined the AP using sticker password (`sunsetcam` or custom)
- [ ] Captive portal sheet appeared within ~10 s (or manual `http://10.42.0.1/` worked; "not secure" warning expected)
- [ ] Form showed scanned SSIDs from `iwlist`
- [ ] Submitting correct credentials joined successfully within 15 s
- [ ] Setup service stopped; supervisor started
- [ ] Cloud: `setup_status` = `registered` or `awaiting_aim` for camera 2
- [ ] Camera 1 untouched: `journalctl -u sunset-cam-supervisor` on camera 1 shows no interruption

### Journalctl commands for failure investigation

```bash
# All three relevant units together, boot-to-now, oldest first:
journalctl -u sunset-cam-boot -u sunset-cam-setup -u sunset-cam-supervisor \
  --no-pager -o short-monotonic | head -200

# Live tail during phone test:
journalctl -u sunset-cam-setup -f

# Check if setup-ap.sh brought up the NM hotspot:
journalctl -u sunset-cam-setup | grep "setup-ap"

# Check NM connection state:
nmcli connection show sunset-setup-ap
nmcli device status

# Check AP IP was assigned (NM shared mode → 10.42.0.1):
ip addr show wlan0
```

---

## Known-good / known-failure quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| AP does not appear | NM hotspot failed to start | `journalctl -u sunset-cam-setup \| grep setup-ap`; check `nmcli device status`; confirm NM is active: `systemctl status NetworkManager` |
| `nmcli connection add` fails | NM not running or wlan0 busy | `sudo systemctl start NetworkManager`; ensure no other process holds wlan0 |
| AP visible but captive sheet never pops | DNS hijack not wired (by design for now) | Browse to `http://10.42.0.1/` manually in a browser on the phone |
| Form loads but no SSIDs | `iwlist scan` failed | In NM shared AP mode the radio is occupied; `nmcli device wifi list` may work instead; `iwlist wlan0 scan` can fail when in AP mode |
| Submit says "could not connect" | Wrong password OR radio can't see that SSID | Verify SSID name is exact; try again |
| Supervisor does not start after join | NM did not save/apply creds | Check `nmcli connection show`; `journalctl -u NetworkManager` |
| Boot dispatcher starts supervisor even with no creds | Stale NM connection profile | `nmcli connection show` and delete any home-wifi profile; reboot |
| SETUP AP reappears ~60 s after boot even though creds were set | Dispatcher fallback: NM joined timed out (bad password / network down) | Check `journalctl -u NetworkManager`; verify SSID/password; reconnect via portal |
| Boot dispatcher runs before NetworkManager is ready | Missing NM ordering (old unit file) | Ensure unit has `After=NetworkManager.service` and `Wants=NetworkManager.service`; `sudo systemctl daemon-reload` |
