# WiFi Onboarding Bring-up Runbook
**Target: bare spare Pi Zero 2 W as camera 2 (camera 1 untouched)**
Date: 2026-06-14

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

The following are flagged in the config files and may need adjustment:

| Item | Default | Where to change |
|---|---|---|
| wlan0 interface name | `wlan0` | `config/hostapd.conf`, `config/dnsmasq-setup.conf`, `systemd/sunset-cam-setup.service` ExecStartPre |
| AP IP address | `10.42.0.1/24` | `systemd/sunset-cam-setup.service` ExecStartPre + `config/dnsmasq-setup.conf` dhcp-option + `src/sunset_cam/setup_app.py` catch-all redirect |
| DHCP subnet | `10.42.0.50-150/24` | `config/dnsmasq-setup.conf` |
| Channel | `6` | `config/hostapd.conf` |
| dhcpcd vs NetworkManager | dhcpcd (Pi OS Lite default) | If NM is active, add `Conflicts=NetworkManager.service` in `sunset-cam-setup.service`; add `interface wlan0 / nohook wpa_supplicant` in `/etc/dhcpcd.conf` to stop dhcpcd from fighting the AP |
| hostapd masked | systemd may mask it at install | Run `sudo systemctl unmask hostapd` before first `systemctl enable hostapd` test |

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
sudo apt update
sudo apt install -y git python3-venv hostapd dnsmasq wpasupplicant \
                    python3-picamera2 i2c-tools

# 3b. hostapd is masked on Pi OS by default — unmask it
sudo systemctl unmask hostapd

# 3c. Disable the hostapd and dnsmasq system services so they are NOT started
#     at boot on their own; sunset-cam-setup.service drives them on demand.
sudo systemctl disable hostapd dnsmasq

# 3d. Clone the firmware repo
sudo git clone https://github.com/<your-org>/sunset-cam-firmware /opt/sunset-cam

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

## Step 4 — Reboot and watch the boot dispatcher

```bash
sudo reboot
```

Watch the dispatcher oneshot as it runs (SSH back in over ethernet after ~30s):

```bash
journalctl -u sunset-cam-boot --no-pager
```

Expected output (no creds case):
```
sunset-cam-boot.service: ExecStart succeeded.
systemctl start sunset-cam-setup.service   ← dispatcher chose SETUP
sunset-cam-boot.service: Deactivating
```

Check that the setup service started:
```bash
systemctl status sunset-cam-setup.service
journalctl -u sunset-cam-setup --no-pager | tail -30
```

Expected: hostapd started, dnsmasq started, Flask captive portal listening.

---

## Step 5 — Phone test (captive portal)

1. On your phone, open WiFi settings.
2. You should see **`Sunset-Cam-XXXX`** (where XXXX is 4 hex chars from the
   Pi's MAC). Connect to it. The network is open (no password).
3. iOS or Android should show a "Sign in to network" / captive-portal sheet
   within ~5 seconds. If it does not, open any browser and navigate to
   `http://10.42.0.1/` manually.
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
- [ ] AP `Sunset-Cam-XXXX` visible on phone
- [ ] Captive portal sheet appeared within ~10 s (or manual `http://10.42.0.1/` worked)
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

# Check if hostapd actually started:
journalctl -u sunset-cam-setup | grep -i hostapd

# Check dnsmasq:
journalctl -u sunset-cam-setup | grep -i dnsmasq

# Check if AP IP was assigned:
ip addr show wlan0
```

---

## Known-good / known-failure quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| AP does not appear | hostapd failed to start | `journalctl -u sunset-cam-setup \| grep -i hostapd`; check if hostapd is still masked (`systemctl status hostapd`) |
| AP visible but captive sheet never pops | dnsmasq not running or wrong interface | Check `address=/#/10.42.0.1` in dnsmasq-setup.conf; `journalctl \| grep dnsmasq` |
| Form loads but no SSIDs | `iwlist scan` failed | Pi must be in AP mode AND have radio; `iwlist wlan0 scan` may need the interface to not be in managed mode |
| Submit says "could not connect" | Wrong password OR radio can't see that SSID | Verify SSID name is exact; try again |
| Supervisor does not start after join | wpa_supplicant did not associate | Check `/etc/wpa_supplicant/wpa_supplicant.conf` was written; `wpa_cli status` |
| Boot dispatcher starts supervisor even with no creds | Stale creds in wpa_supplicant.conf from imager | `grep "network={" /etc/wpa_supplicant/wpa_supplicant.conf` and delete the block |
| `dhcpcd` fights the AP IP | dhcpcd manages wlan0 | Add to `/etc/dhcpcd.conf`: `interface wlan0` + `nohook wpa_supplicant`; reboot |
