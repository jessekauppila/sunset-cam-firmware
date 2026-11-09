#!/bin/sh
# Installs the Sunrise/Sunset agent from the SD card onto a Thingino camera.
# prepare-sd puts this on the card as sunset/install.sh, with a runonce.sh at
# the card's root that calls it with --auto.
#
# Thingino runs <card>/runonce.sh each time the card mounts until it exits 0
# (/lib/mdev/automount, read from Thingino's source; see README "Setup card").
# So with a setup card nobody has to SSH in: the camera installs the agent on
# its first boot with the card inserted.
#
#   sh /mnt/mmcblk0p1/sunset/install.sh          by hand: install and start
#   sh /mnt/mmcblk0p1/sunset/install.sh --auto   from runonce.sh (see below)
#
# --auto takes two boots to finish, on purpose. The config on the card holds
# the camera's device token (and uenv.txt may hold a Wi-Fi password). They are
# only deleted from the card once the installed copy has survived a reboot,
# which proves it landed on the camera's own storage and not in memory (the
# installer that flashes Thingino also boots from this card). Until then --auto
# exits 1 so Thingino calls it again at the next boot.
#
# SUNSET_ROOT prefixes every path on the camera; the tests set it.

R=${SUNSET_ROOT:-}
D=$(cd "$(dirname "$0")" && pwd)
AUTO=0
[ "${1:-}" = "--auto" ] && AUTO=1

CONF_CARD="$D/sunset-agent.conf"
CONF_CAM="$R/etc/sunset-agent.conf"
INIT="$R/etc/init.d/S99sunset-agent"
STAMP="$D/.installed-boot"     # which boot the files were installed in
UENV="$D/../uenv.txt"          # Thingino reads wlan_ssid/wlan_pass from here

say() { echo "sunset-install: $*"; }

boot_id() { cat "$R/proc/sys/kernel/random/boot_id" 2>/dev/null || echo "unknown-$$"; }

# The card's secrets, once they're safely on the camera.
tidy_card() {
	rm -f "$CONF_CARD"
	if [ -f "$UENV" ]; then
		# Thingino re-applies these on every boot, which would undo a Wi-Fi
		# change made later in its web page.
		grep -v -e '^wlan_ssid=' -e '^wlan_pass=' "$UENV" >"$UENV.tmp"
		if [ -s "$UENV.tmp" ]; then mv "$UENV.tmp" "$UENV"; else rm -f "$UENV.tmp" "$UENV"; fi
	fi
	rm -f "$STAMP"
}

# A later boot than the install, and the camera still has the config: done.
if [ -f "$STAMP" ] && [ -f "$CONF_CAM" ] && [ "$(cat "$STAMP")" != "$(boot_id)" ]; then
	if [ ! -f "$CONF_CARD" ] || cmp -s "$CONF_CARD" "$CONF_CAM"; then
		tidy_card
		say "the agent is installed; removed the config and Wi-Fi password from the card"
		exit 0
	fi
fi

install_file() { # SRC DEST MODE
	mkdir -p "$(dirname "$2")" && cp "$1" "$2" && chmod "$3" "$2"
}

if ! { install_file "$D/sunset-agent" "$R/usr/sbin/sunset-agent" 755 &&
	install_file "$D/find-status-led" "$R/usr/sbin/find-status-led" 755 &&
	install_file "$D/S99sunset-agent" "$INIT" 755; }; then
	say "could not copy the agent onto the camera"
	exit 1
fi
say "installed sunset-agent, find-status-led, S99sunset-agent"

START=1
if [ -f "$CONF_CARD" ]; then
	install_file "$CONF_CARD" "$CONF_CAM" 600 || { say "could not install the config"; exit 1; }
	say "installed /etc/sunset-agent.conf"
elif [ ! -f "$CONF_CAM" ]; then
	# A card with no config: leave the template to fill in by hand.
	install_file "$D/sunset-agent.conf.example" "$CONF_CAM" 600
	say "edit /etc/sunset-agent.conf, then: /etc/init.d/S99sunset-agent start"
	START=0
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
if [ -f "$CONF_CARD" ]; then
	say "agent started. The config (with the device token) is still on the card;"
	say "it is removed at the next boot, or delete sunset/sunset-agent.conf yourself."
fi
exit 0
