"""Tests for thingino/prepare-sd, the macOS SD-card writer for Thingino installers.

Runs the real script against a fake `diskutil` (serving plist fixtures for a
set of made-up disks) and a fake `sudo` that "writes" the card to a file, so
the safety rules are checked without touching a real disk. macOS only: the
script uses `plutil`.
"""

from __future__ import annotations

import os
import plistlib
import platform
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "thingino" / "prepare-sd"

pytestmark = pytest.mark.skipif(platform.system() != "Darwin", reason="prepare-sd is macOS-only")

GB = 1000**3

# name: diskutil info keys
DISKS = {
    "disk0": dict(Internal=True, RemovableMedia=False, VirtualOrPhysical="Unknown",
                  BusProtocol="Apple Fabric", TotalSize=500 * GB, MediaName="APPLE SSD"),
    "disk3": dict(Internal=True, RemovableMedia=False, VirtualOrPhysical="Virtual",
                  BusProtocol="Apple Fabric", TotalSize=494 * GB, MediaName="APPLE SSD"),
    "disk4": dict(Internal=False, RemovableMedia=False, VirtualOrPhysical="Physical",
                  BusProtocol="USB", TotalSize=1000 * GB, MediaName="Samsung T7"),
    "disk5": dict(Internal=True, RemovableMedia=True, VirtualOrPhysical="Physical",
                  BusProtocol="Secure Digital", TotalSize=32 * GB, MediaName="SD Card Reader"),
    "disk6": dict(Internal=False, RemovableMedia=True, VirtualOrPhysical="Physical",
                  BusProtocol="USB", TotalSize=16 * GB, MediaName="USB SD Reader"),
    "disk7": dict(Internal=False, RemovableMedia=True, VirtualOrPhysical="Physical",
                  BusProtocol="USB", TotalSize=1000 * GB, MediaName="Big Stick"),
    "disk8": dict(Internal=False, RemovableMedia=True, VirtualOrPhysical="Virtual",
                  BusProtocol="Disk Image", TotalSize=1 * GB, MediaName="Disk Image"),
    "disk9": dict(Internal=True, RemovableMedia=True, VirtualOrPhysical="Physical",
                  BusProtocol="PCI-Express", TotalSize=32 * GB, MediaName="Odd internal"),
}

FAKE_DISKUTIL = r"""#!/bin/sh
F=$FAKE_DIR
echo "diskutil $*" >> "$F/log"
case "$1 $2" in
"list -plist") cat "$F/list.plist" ;;
"info -plist") cat "$F/info-$(echo "$3" | tr / _).plist" 2>/dev/null || exit 1 ;;
"list "*) echo "/dev/$2 (fake):"; echo "   #: TYPE NAME SIZE IDENTIFIER"; echo "   1: Windows_FAT_32 OLDCARD 32 GB ${2}s1" ;;
"unmountDisk "*|"eject "*|"mountDisk "*) ;;
*) echo "fake diskutil: unexpected $*" >&2; exit 2 ;;
esac
"""

# Records every call; emulates `dd` to and from /dev/rdiskN with a file.
FAKE_SUDO = r"""#!/bin/sh
F=$FAKE_DIR
echo "sudo $*" >> "$F/log"
[ "$1" = dd ] || exit 3
shift
args=""
for a in "$@"; do
  case $a in
    if=/dev/r*) args="$args if=$F/card" ;;
    of=/dev/r*) args="$args of=$F/card" ;;
    status=*) ;;
    *) args="$args $a" ;;
  esac
done
dd $args
if [ -n "${FAKE_CORRUPT:-}" ] && echo "$*" | grep -q 'of=/dev/r'; then printf X | dd of="$F/card" bs=1 seek=10 conv=notrunc 2>/dev/null; fi
"""


@pytest.fixture
def env(tmp_path):
    fake = tmp_path / "fake"
    bin_ = tmp_path / "bin"
    fake.mkdir()
    bin_.mkdir()
    (fake / "list.plist").write_bytes(plistlib.dumps({"WholeDisks": list(DISKS)}))
    for name, info in DISKS.items():
        (fake / f"info-{name}.plist").write_bytes(
            plistlib.dumps({"DeviceIdentifier": name, "WholeDisk": True, **info}))
    (fake / "info-_.plist").write_bytes(plistlib.dumps(
        {"ParentWholeDisk": "disk3", "APFSPhysicalStores": [{"APFSPhysicalStore": "disk0s2"}]}))
    for n, body in (("diskutil", FAKE_DISKUTIL), ("sudo", FAKE_SUDO)):
        (bin_ / n).write_text(body)
        (bin_ / n).chmod(0o755)
    img = tmp_path / "sd.img"
    img.write_bytes(os.urandom(3 * 1024 * 1024))
    e = dict(os.environ, FAKE_DIR=str(fake), PATH=f"{bin_}:{os.environ['PATH']}",
             PREPARE_SD_CACHE=str(tmp_path / "cache"))
    return fake, img, e


def run(env, *args, answer=""):
    fake, img, e = env
    return subprocess.run([str(SCRIPT), *args], input=answer, text=True, capture_output=True, env=e)


def log(env):
    p = env[0] / "log"
    return p.read_text() if p.exists() else ""


def test_list_accepts_only_removable_sd_disks(env):
    r = run(env, "--list")
    assert r.returncode == 0, r.stderr
    lines = {l.split()[1]: l for l in r.stdout.splitlines() if l.startswith("  ")}
    ok = {d for d, l in lines.items() if l.lstrip().startswith("OK")}
    assert ok == {"disk5", "disk6"}  # built-in SD slot and a USB reader
    assert "running system" in lines["disk0"]
    assert "running system" in lines["disk3"]
    assert "not removable" in lines["disk4"]
    assert "256 GB" in lines["disk7"]
    assert "virtual" in lines["disk8"]
    assert "PCI-Express" in lines["disk9"]
    assert "sudo" not in log(env)


def test_two_candidates_need_explicit_disk(env):
    r = run(env, str(env[1]))
    assert r.returncode != 0
    assert "--disk" in r.stderr
    assert "sudo" not in log(env)


@pytest.mark.parametrize("disk", ["disk0", "disk4", "disk7", "disk9", "disk42"])
def test_refuses_unsafe_disk_even_when_named(env, disk):
    r = run(env, "--disk", disk, str(env[1]), answer=f"{disk}\n")
    assert r.returncode != 0
    assert f"refusing {disk}" in r.stderr
    assert "sudo" not in log(env)
    assert "unmountDisk" not in log(env)


@pytest.mark.parametrize("answer", ["", "y\n", "yes\n", "disk6\n", "/dev/disk5\n"])
def test_wrong_confirmation_writes_nothing(env, answer):
    r = run(env, "--disk", "disk5", str(env[1]), answer=answer)
    assert r.returncode != 0
    assert "nothing was written" in r.stderr
    assert "sudo" not in log(env)
    assert "unmountDisk" not in log(env)


def test_writes_verifies_and_ejects(env):
    fake, img, _ = env
    r = run(env, "--disk", "/dev/rdisk5", str(img), answer="disk5\n")
    assert r.returncode == 0, r.stderr
    assert (fake / "card").read_bytes() == img.read_bytes()
    calls = log(env)
    assert f"sudo dd if={img} of=/dev/rdisk5" in calls
    assert calls.index("diskutil unmountDisk /dev/disk5") < calls.index("sudo dd")
    assert "diskutil eject /dev/disk5" in calls
    assert "card matches the image" in r.stdout
    assert "OLDCARD" in r.stdout  # shows what's on the card before erasing


def test_unzips_installer(env, tmp_path):
    fake, img, _ = env
    zp = tmp_path / "x.zip"
    subprocess.run(["zip", "-jq", str(zp), str(img)], check=True)
    r = run(env, "--disk", "disk6", str(zp), answer="disk6\n")
    assert r.returncode == 0, r.stderr
    assert (fake / "card").read_bytes() == img.read_bytes()


def test_bad_verification_fails_loudly(env):
    fake, img, e = env
    e["FAKE_CORRUPT"] = "1"
    r = run(env, "--disk", "disk5", str(img), answer="disk5\n")
    assert r.returncode != 0
    assert "verification FAILED" in r.stderr
    assert "eject" not in log(env)
