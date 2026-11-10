#!/bin/sh
# Installs the Sunrise/Sunset agent from the SD card onto a Thingino camera.
# prepare-sd puts this on the card as sunset/install.sh, with a runonce.sh at
# the card's root that calls it with --auto.
#
# Thingino runs <card>/runonce.sh each time the card mounts until it exits 0
# (/lib/mdev/automount; seen working on build 2026-11-05). So with a setup card
# nobody has to SSH in: the camera installs the agent on its first boot with
# the card inserted.
#
#   sh /mnt/mmcblk0p1/sunset/install.sh          by hand: install and start
#   sh /mnt/mmcblk0p1/sunset/install.sh --auto   from runonce.sh (see below)
#
# --auto takes two boots to finish, on purpose. The card holds the camera's
# device token, maybe a root password and maybe a Wi-Fi password (uenv.txt).
# They are only deleted from the card once the installed copy has survived a
# reboot, which proves it landed on the camera's own storage and not in memory
# (the installer that flashes Thingino also boots from this card). Until then
# --auto exits 1 so Thingino calls it again at the next boot.
#
# FILE NAMES ON THE CARD. Thingino's FAT driver matches a name against any
# file whose name is the *start* of it: with "sunset-agent" on the card,
# "sunset-agent.conf" opens sunset-agent, whether or not a real
# sunset-agent.conf exists, and writing to it overwrites sunset-agent (seen on
# the first Cam v3: the agent was installed as its own config). So no name in
# this folder may be the start of another. The names below are short and
# unrelated for that reason; keep it that way (tests/test_card_install.py
# checks). Nothing is ever written next to uenv.txt under a longer name.
#
# COMMANDS. Thingino's busybox is small: there is no cmp, for one (found on the
# camera; the first version of this script could never finish because of it).
# The tests run this with only the commands seen on a Cam v3 on the PATH, so a
# new one has to be added there, after checking the camera has it.
#
# SUNSET_ROOT prefixes every path on the camera, and SUNSET_CHPASSWD replaces
# chpasswd; the tests set both.

R=${SUNSET_ROOT:-}
D=$(cd "$(dirname "$0")" && pwd)
AUTO=0
[ "${1:-}" = "--auto" ] && AUTO=1

# On the card (see FILE NAMES above)      -> on the camera
AGENT_CARD="$D/agent.sh"                  # /usr/sbin/sunset-agent
INIT_CARD="$D/initd.sh"                   # /etc/init.d/S99sunset-agent
LED_CARD="$D/findled.sh"                  # /usr/sbin/find-status-led
EXAMPLE_CARD="$D/example.conf"            # /etc/sunset-agent.conf, if no config
CONF_CARD="$D/camera.conf"                # /etc/sunset-agent.conf (device token)
PASS_CARD="$D/rootpass.txt"               # root's password (one line)
STAMP="$D/stamp.txt"                      # which boot the files were installed in
UENV="$D/../uenv.txt"                     # Thingino reads wlan_ssid/wlan_pass here

CONF_CAM="$R/etc/sunset-agent.conf"
INIT="$R/etc/init.d/S99sunset-agent"

say() { echo "sunset-install: $*"; }

boot_id() { cat "$R/proc/sys/kernel/random/boot_id" 2>/dev/null || echo "unknown-$$"; }

# on_card FILE: is it really there? Asks the folder's listing, which does not
# share the driver's name matching, rather than opening the name.
on_card() { ls -1a "$(dirname "$1")" 2>/dev/null | grep -qxF "$(basename "$1")"; }

# same FILE FILE: do two small text files say the same thing? (No cmp here.)
same() { [ "$(cat "$1" 2>/dev/null)" = "$(cat "$2" 2>/dev/null)" ]; }

# The card's secrets, once they're safely on the camera.
tidy_card() {
	! on_card "$CONF_CARD" || rm -f "$CONF_CARD"
	! on_card "$PASS_CARD" || rm -f "$PASS_CARD"
	if on_card "$UENV"; then
		# Thingino re-applies these on every boot, which would undo a Wi-Fi
		# change made later in its web page. The work file lives on the camera:
		# a longer name beside uenv.txt would be uenv.txt itself.
		_t="$R/tmp/sunset-uenv.$$"
		mkdir -p "$R/tmp"
		grep -v -e '^wlan_ssid=' -e '^wlan_pass=' "$UENV" >"$_t"
		if [ -s "$_t" ]; then cat "$_t" >"$UENV"; else rm -f "$UENV"; fi
		rm -f "$_t"
	fi
	! on_card "$STAMP" || rm -f "$STAMP"
}

# A later boot than the install, and the camera still has the config: done.
if on_card "$STAMP" && [ -f "$CONF_CAM" ] && [ "$(cat "$STAMP")" != "$(boot_id)" ]; then
	if ! on_card "$CONF_CARD" || same "$CONF_CARD" "$CONF_CAM"; then
		tidy_card
		say "the agent is installed; removed the config and passwords from the card"
		exit 0
	fi
fi

install_file() { # SRC DEST MODE
	mkdir -p "$(dirname "$2")" && cp "$1" "$2" && chmod "$3" "$2"
}

for f in "$AGENT_CARD" "$INIT_CARD" "$LED_CARD"; do
	on_card "$f" || { say "the card has no $(basename "$f"); nothing installed"; exit 1; }
done
if ! { install_file "$AGENT_CARD" "$R/usr/sbin/sunset-agent" 755 &&
	install_file "$LED_CARD" "$R/usr/sbin/find-status-led" 755 &&
	install_file "$INIT_CARD" "$INIT" 755; }; then
	say "could not copy the agent onto the camera"
	exit 1
fi
say "installed sunset-agent, find-status-led, S99sunset-agent"

START=1
if on_card "$CONF_CARD"; then
	install_file "$CONF_CARD" "$CONF_CAM" 600 || { say "could not install the config"; exit 1; }
	say "installed /etc/sunset-agent.conf"
elif [ ! -f "$CONF_CAM" ]; then
	# A card with no config: leave the template to fill in by hand.
	install_file "$EXAMPLE_CARD" "$CONF_CAM" 600
	say "edit /etc/sunset-agent.conf, then: /etc/init.d/S99sunset-agent start"
	START=0
fi

# A card that carries the Wi-Fi skips Thingino's setup page, which is where a
# root password is normally chosen; without this the camera would sit on the
# network as root/root.
if on_card "$PASS_CARD"; then
	_pw=$(head -n 1 "$PASS_CARD" | tr -d '\r\n')
	# The same call Thingino's setup page makes (/var/www-portal/x/api.cgi).
	if [ -n "$_pw" ] && printf 'root:%s\n' "$_pw" | ${SUNSET_CHPASSWD:-chpasswd -c sha512} >/dev/null 2>&1; then
		say "set the root password from the card"
	else
		say "could NOT set the root password; it is still Thingino's default"
	fi
fi

boot_id >"$STAMP"

# The camera's own boot starts the agent from now on. Start it this once too:
# this boot's list of init scripts was read before ours existed.
if [ "$START" = 1 ]; then
	"$INIT" restart >/dev/null 2>&1 || "$INIT" start >/dev/null 2>&1 ||
		say "could not start the agent now; it starts at the next boot"
fi

if [ "$AUTO" = 1 ]; then
	say "installed; the card is tidied after the next restart"
	exit 1
fi
if on_card "$CONF_CARD"; then
	say "agent started. The config (with the device token) is still on the card;"
	say "it is removed at the next boot, or delete sunset/camera.conf yourself."
fi
exit 0
