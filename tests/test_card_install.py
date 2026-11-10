"""Tests for thingino/card-install.sh, the script a setup card runs on the camera.

Runs the real script with SUNSET_ROOT pointing at a pretend camera filesystem
and a pretend SD card. The point of most of these: the card holds the camera's
device token (and maybe a Wi-Fi password), and they may only leave the card
once the installed copy has survived a reboot.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

THINGINO = Path(__file__).resolve().parent.parent / "thingino"
SH = shutil.which("dash") or shutil.which("sh")

# What the script may call: commands seen on the Cam v3 (Thingino 2026-11-05).
# Its busybox has no cmp, which the first version of the script relied on; the
# tests passed on a Mac and the card could never have finished on a camera. So
# the script runs here with these and nothing else on its PATH.
CAMERA_COMMANDS = ("cat cp chmod mkdir rm ls grep head tr dirname basename sed awk cut "
                   "mktemp mv touch sleep wc sort").split()

CONF = 'CAMERA_ID="7"\nDEVICE_TOKEN="secret-token"\n'
# Stands in for the agent's init script: records how it was called.
FAKE_INIT = '#!/bin/sh\necho "$1" >>"$(dirname "$0")/../../init.log"\n'
# Stands in for chpasswd: records the "user:password" line it was given.
FAKE_CHPASSWD = '#!/bin/sh\ncat >>"$CHPASSWD_LOG"\n'


class Rig:
    def __init__(self, tmp: Path):
        self.card = tmp / "card"
        self.sunset = self.card / "sunset"
        self.sunset.mkdir(parents=True)
        shutil.copy(THINGINO / "card-install.sh", self.sunset / "install.sh")
        (self.sunset / "agent.sh").write_text("#!/bin/sh\n# agent\n")
        (self.sunset / "findled.sh").write_text("#!/bin/sh\n# led\n")
        (self.sunset / "initd.sh").write_text(FAKE_INIT)
        (self.sunset / "example.conf").write_text('CAMERA_ID=""\n')
        (self.sunset / "camera.conf").write_text(CONF)
        self.tmp = tmp
        self.chpasswd = tmp / "chpasswd"
        self.chpasswd.write_text(FAKE_CHPASSWD)
        self.chpasswd.chmod(0o755)
        self.chpasswd_log = tmp / "chpasswd.log"
        self.bin = tmp / "camera-bin"
        self.bin.mkdir()
        for c in CAMERA_COMMANDS:
            (self.bin / c).symlink_to(shutil.which(c))
        self.root = self.new_camera("root")

    def new_camera(self, name: str) -> Path:
        """A camera filesystem with nothing of ours on it."""
        root = self.tmp / name
        (root / "proc/sys/kernel/random").mkdir(parents=True)
        self.root = root
        self.boot("boot-1")
        return root

    def boot(self, boot_id: str):
        (self.root / "proc/sys/kernel/random/boot_id").write_text(boot_id + "\n")

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([SH, str(self.sunset / "install.sh"), *args],
                              env={"SUNSET_ROOT": str(self.root), "PATH": str(self.bin),
                                   "SUNSET_CHPASSWD": str(self.chpasswd),
                                   "CHPASSWD_LOG": str(self.chpasswd_log)},
                              capture_output=True, text=True)

    @property
    def card_conf(self) -> Path:
        return self.sunset / "camera.conf"

    @property
    def card_pass(self) -> Path:
        return self.sunset / "rootpass.txt"

    def passwords_set(self) -> list[str]:
        return self.chpasswd_log.read_text().splitlines() if self.chpasswd_log.exists() else []

    @property
    def cam_conf(self) -> Path:
        return self.root / "etc/sunset-agent.conf"

    def init_calls(self) -> list[str]:
        log = self.root / "init.log"
        return log.read_text().split() if log.exists() else []


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def test_first_boot_installs_and_starts_but_keeps_the_card_as_it_is(rig):
    r = rig.run("--auto")
    assert r.returncode == 1, r.stdout + r.stderr  # not finished: Thingino will call again
    assert mode(rig.root / "usr/sbin/sunset-agent") == 0o755
    assert mode(rig.root / "usr/sbin/find-status-led") == 0o755
    assert mode(rig.root / "etc/init.d/S99sunset-agent") == 0o755
    assert rig.cam_conf.read_text() == CONF
    assert mode(rig.cam_conf) == 0o600
    assert rig.init_calls() == ["restart"]
    assert rig.card_conf.exists()  # the token stays until a reboot proves the copy stuck


def test_same_boot_again_still_does_not_touch_the_card(rig):
    rig.run("--auto")
    r = rig.run("--auto")  # card pulled and pushed back in without a reboot
    assert r.returncode == 1
    assert rig.card_conf.exists()


def test_next_boot_takes_the_secrets_off_the_card_and_finishes(rig):
    (rig.card / "uenv.txt").write_text("bootdelay=1\nwlan_ssid=Home Net\nwlan_pass=p=ss word\n")
    rig.run("--auto")
    rig.boot("boot-2")
    r = rig.run("--auto")
    assert r.returncode == 0, r.stdout + r.stderr  # Thingino now marks runonce as done
    assert not rig.card_conf.exists()
    assert (rig.card / "uenv.txt").read_text() == "bootdelay=1\n"  # only our two keys go
    assert rig.cam_conf.read_text() == CONF
    assert rig.init_calls() == ["restart"]  # the camera's own boot starts it from now on


def test_a_wifi_only_uenv_is_removed_entirely(rig):
    (rig.card / "uenv.txt").write_text("wlan_ssid=Home\nwlan_pass=pw\n")
    rig.run("--auto")
    rig.boot("boot-2")
    assert rig.run("--auto").returncode == 0
    assert not (rig.card / "uenv.txt").exists()


def test_an_install_into_memory_does_not_cost_the_token(rig):
    """The card that flashes Thingino boots its own installer first. If that
    environment ran the script, the copy would vanish on reboot."""
    rig.run("--auto")                 # boot 1: lands in the installer's memory
    rig.new_camera("flashed")         # boot 2: the real, freshly flashed camera
    rig.boot("boot-2")
    r = rig.run("--auto")
    assert r.returncode == 1
    assert rig.card_conf.exists()     # still there, and now installed for real
    assert rig.cam_conf.read_text() == CONF
    rig.boot("boot-3")
    assert rig.run("--auto").returncode == 0
    assert not rig.card_conf.exists()


def test_a_card_with_a_different_identity_replaces_the_config(rig):
    rig.run("--auto")
    rig.card_conf.write_text('CAMERA_ID="8"\n')  # the card was remade for another camera row
    rig.boot("boot-2")
    r = rig.run("--auto")
    assert r.returncode == 1
    assert rig.cam_conf.read_text() == 'CAMERA_ID="8"\n'
    assert rig.card_conf.exists()


def test_by_hand_installs_starts_and_reports_success(rig):
    r = rig.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert rig.cam_conf.read_text() == CONF
    assert rig.init_calls() == ["restart"]
    assert "still on the card" in r.stdout


def test_without_a_config_it_leaves_the_template_and_does_not_start(rig):
    rig.card_conf.unlink()
    r = rig.run()
    assert r.returncode == 0
    assert rig.cam_conf.read_text() == 'CAMERA_ID=""\n'
    assert rig.init_calls() == []
    assert "edit /etc/sunset-agent.conf" in r.stdout


def test_an_agent_only_card_keeps_the_cameras_own_config(rig):
    rig.run("--auto")
    rig.boot("boot-2")
    rig.run("--auto")                              # finished; card has no config now
    (rig.sunset / "agent.sh").write_text("#!/bin/sh\n# agent v2\n")
    rig.boot("boot-3")
    r = rig.run("--auto")                          # an update card
    assert r.returncode == 1
    assert "agent v2" in (rig.root / "usr/sbin/sunset-agent").read_text()
    assert rig.cam_conf.read_text() == CONF
    assert rig.init_calls() == ["restart", "restart"]


# ---- root password -----------------------------------------------------------

def test_the_cards_root_password_is_set_and_leaves_the_card_with_the_token(rig):
    rig.card_pass.write_text("s3cret-Pw\n")
    r = rig.run("--auto")
    assert r.returncode == 1
    assert rig.passwords_set() == ["root:s3cret-Pw"]
    assert "set the root password" in r.stdout
    assert rig.card_pass.exists()      # same rule as the token: not until a reboot
    rig.boot("boot-2")
    assert rig.run("--auto").returncode == 0
    assert not rig.card_pass.exists()
    assert not rig.card_conf.exists()
    assert rig.passwords_set() == ["root:s3cret-Pw"]  # not set a second time


def test_no_password_on_the_card_leaves_the_cameras_password_alone(rig):
    rig.run("--auto")
    assert rig.passwords_set() == []


def test_a_password_that_cannot_be_set_is_reported_not_hidden(rig):
    rig.card_pass.write_text("pw\n")
    rig.chpasswd.write_text("#!/bin/sh\nexit 1\n")
    r = rig.run("--auto")
    assert "could NOT set the root password" in r.stdout
    assert rig.cam_conf.read_text() == CONF  # the rest of the install still happened


# ---- the card's file names ---------------------------------------------------

def test_a_card_missing_the_agent_installs_nothing(rig):
    (rig.sunset / "agent.sh").unlink()
    r = rig.run("--auto")
    assert r.returncode == 1
    assert "no agent.sh" in r.stdout
    assert not rig.cam_conf.exists()


def test_no_card_file_name_is_the_start_of_another():
    """Thingino's FAT driver opens "sunset-agent" when asked for
    "sunset-agent.conf" (see card-install.sh). Every name the script reads or
    writes on the card must therefore be unrelated to every other."""
    script = (THINGINO / "card-install.sh").read_text()
    names = set(re.findall(r'="\$D/(?:\.\./)?([A-Za-z0-9._-]+)"', script))
    assert {"agent.sh", "initd.sh", "findled.sh", "example.conf", "camera.conf",
            "rootpass.txt", "stamp.txt", "uenv.txt"} <= names
    names |= {"install.sh", "runonce.sh", "runonce.done"}
    low = sorted(n.lower() for n in names)
    clashes = [(a, b) for a in low for b in low if a != b and b.startswith(a)]
    assert clashes == []


def test_nothing_is_written_beside_uenv_under_a_longer_name(rig):
    # "uenv.txt.tmp" on the camera *is* uenv.txt: writing it would empty the file.
    (rig.card / "uenv.txt").write_text("bootdelay=1\nwlan_ssid=Home\nwlan_pass=pw\n")
    rig.run("--auto")
    rig.boot("boot-2")
    rig.run("--auto")
    assert sorted(p.name for p in rig.card.iterdir()) == ["sunset", "uenv.txt"]
    assert "$UENV." not in (THINGINO / "card-install.sh").read_text()


def test_the_script_only_calls_commands_the_camera_has(rig):
    # Every path through the script above ran with CAMERA_COMMANDS alone. This
    # pins the one that bit: a missing command must not pass silently.
    assert "cmp" not in CAMERA_COMMANDS
    rig.run("--auto")
    rig.boot("boot-2")
    r = rig.run("--auto")
    assert r.returncode == 0
    assert "not found" not in r.stdout + r.stderr
