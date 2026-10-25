"""Drives on Windows, through PowerShell's Get-Disk (Windows 8 and later)."""

import json
import subprocess

from . import Device
from ..core.rawdisk import is_admin

# BusType comes as a name or, depending on the PowerShell version, its number
REMOVABLE_BUSES = {"usb": "usb", "7": "usb", "sd": "mmc", "12": "mmc", "mmc": "mmc", "13": "mmc"}

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
@(Get-Disk | ForEach-Object {
    $d = $_
    $fs = (Get-Partition -DiskNumber $d.Number | Get-Volume | Select-Object -First 1).FileSystem
    [pscustomobject]@{ Number = $d.Number; Name = $d.FriendlyName; Size = $d.Size;
                       Bus = [string]$d.BusType; Fs = $fs; Boot = $d.IsBoot; System = $d.IsSystem }
}) | ConvertTo-Json -Compress
"""


def parse_disks(text, readable=False):
    """Removable disks out of the script's JSON. Never the one Windows runs from."""
    data = json.loads(text or "[]")
    if isinstance(data, dict):
        data = [data]
    found = []
    for d in data:
        bus = REMOVABLE_BUSES.get(str(d.get("Bus", "")).lower())
        if not bus or d.get("Boot") or d.get("System") or not d.get("Size"):
            continue
        found.append(Device(f"\\\\.\\PhysicalDrive{d['Number']}", (d.get("Name") or "").strip()
                            or f"Disco {d['Number']}", int(d["Size"]), bus,
                            (d.get("Fs") or "").lower(), readable))
    return found


def list_removable():
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                             capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    if res.returncode != 0:
        return []
    try:
        return parse_disks(res.stdout, readable=is_admin())
    except ValueError:
        return []
