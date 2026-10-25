"""Drives on macOS, through diskutil."""

import os
import plistlib
import subprocess

from . import Device


def _plist(*args):
    res = subprocess.run(["diskutil", *args, "-plist"], capture_output=True, timeout=20)
    return plistlib.loads(res.stdout) if res.returncode == 0 and res.stdout else {}


def describe(info, partitions):
    """A Device from 'diskutil info -plist diskN', or None if it is not removable."""
    if info.get("Internal", True) and not info.get("RemovableMediaOrExternalDevice"):
        return None
    if not info.get("WholeDisk") or not info.get("TotalSize"):
        return None
    bus = (info.get("BusProtocol") or "").lower()
    ident = info["DeviceIdentifier"]
    fs = next((p.get("FilesystemType") or p.get("Content") or "" for p in partitions
               if p.get("FilesystemType") or p.get("Content")), "")
    raw = f"/dev/r{ident}"      # the raw device: much faster to read whole
    return Device(raw, (info.get("MediaName") or ident).strip(), int(info["TotalSize"]),
                  "usb" if "usb" in bus else bus or "external", fs.lower(), os.access(raw, os.R_OK))


def list_removable():
    try:
        listing = _plist("list", "external", "physical")
        found = []
        for disk in listing.get("AllDisksAndPartitions", []):
            ident = disk.get("DeviceIdentifier")
            if not ident:
                continue
            dev = describe(_plist("info", ident), disk.get("Partitions", []))
            if dev:
                found.append(dev)
        return found
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException):
        return []
