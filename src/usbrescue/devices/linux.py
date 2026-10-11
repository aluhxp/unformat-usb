import json
import os
import subprocess

from . import Device

SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/home", "/usr", "/var", "[SWAP]")


def _mounts(node):
    out = [m for m in node.get("mountpoints") or [] if m]
    for child in node.get("children") or []:
        out += _mounts(child)
    return out


def parse_lsblk(text):
    """Whole disks that are removable or on USB, and hold no system mount."""
    found = []
    for disk in json.loads(text).get("blockdevices", []):
        if disk.get("type") != "disk":
            continue
        if not (disk.get("rm") or disk.get("hotplug") or disk.get("tran") in ("usb", "mmc")):
            continue
        if any(m in SYSTEM_MOUNTS for m in _mounts(disk)):
            continue
        if not disk.get("size"):
            continue        # an empty card reader slot
        parts = disk.get("children") or []
        fs = disk.get("fstype") or next((p.get("fstype") for p in parts if p.get("fstype")), "") or ""
        path = "/dev/" + disk["name"]
        found.append(Device(path, (disk.get("model") or "").strip() or disk["name"],
                            int(disk["size"]), disk.get("tran") or "", fs,
                            os.access(path, os.R_OK)))
    return found


def list_removable():
    try:
        res = subprocess.run(
            ["lsblk", "--json", "--bytes", "-o", "NAME,SIZE,MODEL,TRAN,RM,HOTPLUG,TYPE,FSTYPE,MOUNTPOINTS"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_lsblk(res.stdout) if res.returncode == 0 else []
