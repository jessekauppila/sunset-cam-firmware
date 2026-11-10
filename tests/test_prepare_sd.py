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
"eraseDisk "*)
  # eraseDisk FS LABEL SCHEME /dev/diskN -> a fake mounted volume
  d=$(basename "$5"); mkdir -p "$F/vol-$d"
  printf '<?xml version="1.0"?><plist version="1.0"><dict><key>MountPoint</key><string>%s</string></dict></plist>' "$F/vol-$d" > "$F/info-${d}s1.plist" ;;
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
d=$(echo "$*" | sed -n 's|.*of=/dev/r\(disk[0-9]*\).*|\1|p')
[ -n "$d" ] || exit 0
# What macOS does the moment the write finishes: mounts the card's FAT32
# volume. The files on it are the ones in the image.
mkdir -p "$F/vol-$d"
/bin/cp "$F/imgvol/"* "$F/vol-$d/"
printf '<?xml version="1.0"?><plist version="1.0"><dict><key>MountPoint</key><string>%s</string></dict></plist>' "$F/vol-$d" > "$F/info-${d}s1.plist"
if [ -n "${FAKE_CORRUPT:-}" ]; then printf X | dd of="$F/card" bs=1 seek=10 conv=notrunc 2>/dev/null; fi
if [ -n "${FAKE_CORRUPT_FILE:-}" ]; then printf X | dd of="$F/vol-$d/thingino-board_a.bin" bs=1 seek=5 conv=notrunc 2>/dev/null; fi
"""

# Serves a directory as the image's mounted volume, in hdiutil's own
# "device<TAB>type<TAB>mount point" output.
FAKE_HDIUTIL = r"""#!/bin/sh
F=$FAKE_DIR
echo "hdiutil $*" >> "$F/log"
case $1 in
attach)
  printf '/dev/disk99          \tFDisk_partition_scheme         \t\n'
  printf '/dev/disk99s1        \tWindows_FAT_32                 \t%s\n' "$F/imgvol" ;;
detach) ;;
*) echo "fake hdiutil: unexpected $*" >&2; exit 2 ;;
esac
"""


# Real cp, but with FAKE_CORRUPT_COPY set it flips a byte of the destination so
# the script's byte-compare has something to catch.
FAKE_CP = r"""#!/bin/sh
/bin/cp "$@" || exit $?
[ -n "${FAKE_CORRUPT_COPY:-}" ] || exit 0
for last; do :; done
[ -f "$last" ] && printf X | dd of="$last" bs=1 seek=1 conv=notrunc 2>/dev/null
exit 0
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
    imgvol = fake / "imgvol"  # the files inside the installer image
    imgvol.mkdir()
    (imgvol / "factory_t31_ZMC6tiIDQN").write_bytes(os.urandom(2048))
    # Starts with zeros so the fakes' "flip a byte to X" always changes it.
    (imgvol / "thingino-board_a.bin").write_bytes(bytes(16) + os.urandom(4080))
    (imgvol / "thingino-board_b.bin").write_bytes(os.urandom(4096))
    for n, body in (("diskutil", FAKE_DISKUTIL), ("sudo", FAKE_SUDO), ("cp", FAKE_CP),
                    ("hdiutil", FAKE_HDIUTIL)):
        (bin_ / n).write_text(body)
        (bin_ / n).chmod(0o755)
    img = tmp_path / "sd.img"
    img.write_bytes(bytes(16) + os.urandom(3 * 1024 * 1024 - 16))
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
    assert "all 3 files match the image" in r.stdout
    assert "hdiutil detach" in calls  # the image is not left mounted
    assert "OLDCARD" in r.stdout  # shows what's on the card before erasing


def test_unzips_installer(env, tmp_path):
    fake, img, _ = env
    zp = tmp_path / "x.zip"
    subprocess.run(["zip", "-jq", str(zp), str(img)], check=True)
    r = run(env, "--disk", "disk6", str(zp), answer="disk6\n")
    assert r.returncode == 0, r.stderr
    assert (fake / "card").read_bytes() == img.read_bytes()


def test_bad_partition_table_fails_loudly(env):
    fake, img, e = env
    e["FAKE_CORRUPT"] = "1"
    r = run(env, "--disk", "disk5", str(img), answer="disk5\n")
    assert r.returncode != 0
    assert "verification FAILED: the partition table" in r.stderr
    assert "eject" not in log(env)


def test_a_file_that_differs_from_the_image_fails_loudly(env):
    fake, img, e = env
    e["FAKE_CORRUPT_FILE"] = "1"
    r = run(env, "--disk", "disk5", str(img), answer="disk5\n")
    assert r.returncode != 0
    assert "MISMATCH: thingino-board_a.bin" in r.stdout
    assert "verification FAILED: files on disk5" in r.stderr
    calls = log(env)
    assert "eject" not in calls
    assert "hdiutil detach" in calls


def test_files_macos_adds_to_the_card_do_not_fail_verification(env):
    # The reason the old byte-for-byte check could never pass: macOS mounts the
    # fresh volume and writes to it. Extra files on the card are fine.
    fake, img, e = env
    vol = fake / "vol-disk5"
    (vol / ".fseventsd").mkdir(parents=True)
    (vol / ".fseventsd" / "fseventsd-uuid").write_text("x")
    r = run(env, "--disk", "disk5", str(img), answer="disk5\n")
    assert r.returncode == 0, r.stderr
    assert "all 3 files match the image" in r.stdout


# ---- files mode (--fat32 / --copy / --revert) -------------------------------

def test_files_mode_erases_fat32_and_copies_named_files(env, tmp_path):
    fake, _img, _ = env
    a = tmp_path / "stock.bin"; a.write_bytes(os.urandom(4096))
    b = tmp_path / "notes.txt"; b.write_text("hi")
    r = run(env, "--disk", "disk5", "--copy", f"{a}:recovery_wyzepan3.bin", "--copy", str(b), answer="disk5\n")
    assert r.returncode == 0, r.stderr
    calls = log(env)
    assert "diskutil eraseDisk FAT32 SUNSET MBRFormat /dev/disk5" in calls
    assert "sudo" not in calls  # no dd in files mode
    assert calls.index("unmountDisk /dev/disk5") < calls.index("eraseDisk")
    assert "diskutil eject /dev/disk5" in calls
    vol = fake / "vol-disk5"
    assert (vol / "recovery_wyzepan3.bin").read_bytes() == a.read_bytes()
    assert (vol / "notes.txt").read_text() == "hi"
    assert "recovery_wyzepan3.bin  <-" in r.stdout  # shown before confirming


def test_revert_card_is_only_autoupdate_full_bin(env, tmp_path):
    fake, _img, _ = env
    bk = tmp_path / "combined_backup.bin"; bk.write_bytes(os.urandom(2048))
    r = run(env, "--disk", "disk6", "--revert", str(bk), answer="disk6\n")
    assert r.returncode == 0, r.stderr
    assert "eraseDisk FAT32 WYZE_REVERT MBRFormat /dev/disk6" in log(env)
    vol = fake / "vol-disk6"
    assert sorted(p.name for p in vol.iterdir()) == ["autoupdate-full.bin"]
    assert (vol / "autoupdate-full.bin").read_bytes() == bk.read_bytes()


def test_files_mode_rejects_installer_arg_and_missing_files(env, tmp_path):
    r = run(env, "--fat32", "--copy", str(env[1]), str(env[1]), answer="disk5\n")
    assert r.returncode != 0 and "takes no installer" in r.stderr
    r = run(env, "--copy", str(tmp_path / "nope.bin"), answer="disk5\n")
    assert r.returncode != 0 and "no such file" in r.stderr
    r = run(env, "--fat32", "--disk", "disk5", answer="disk5\n")
    assert r.returncode != 0 and "at least one --copy" in r.stderr
    assert "eraseDisk" not in log(env)


@pytest.mark.parametrize("disk", ["disk0", "disk4", "disk9"])
def test_files_mode_refuses_unsafe_disk(env, tmp_path, disk):
    f = tmp_path / "x.bin"; f.write_bytes(b"x" * 100)
    r = run(env, "--disk", disk, "--copy", str(f), answer=f"{disk}\n")
    assert r.returncode != 0 and f"refusing {disk}" in r.stderr
    assert "eraseDisk" not in log(env)


def test_files_mode_wrong_confirmation_writes_nothing(env, tmp_path):
    f = tmp_path / "x.bin"; f.write_bytes(b"x" * 100)
    r = run(env, "--disk", "disk5", "--copy", str(f), answer="yes\n")
    assert r.returncode != 0 and "nothing was written" in r.stderr
    assert "eraseDisk" not in log(env) and "unmountDisk" not in log(env)


def test_files_mode_copy_verification_failure_is_fatal(env, tmp_path):
    fake, _img, e = env
    e["FAKE_CORRUPT_COPY"] = "1"
    f = tmp_path / "x.bin"; f.write_bytes(b"x" * 100)
    r = run(env, "--disk", "disk5", "--copy", str(f), answer="disk5\n")
    assert r.returncode != 0
    assert "verification FAILED" in r.stderr
    assert "eject" not in log(env)
