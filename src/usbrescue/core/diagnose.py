"""A look that takes seconds, before the long scan: what did the format leave?

It reads the boot sector, the FAT, the start of the volume and a spread of
samples. Its answer is a forecast, not a promise: only the scan confirms it,
and it must never be used to turn someone away."""

import struct
from dataclasses import dataclass

from .boot import read_boot
from .exfat import SYSTEM_NAMES, parse_dir
from .scan import find_exfat_roots

PROBE = 64 * 1024 * 1024    # roots live near the start of a volume
SAMPLE = 4096


@dataclass
class Diagnosis:
    current_fs: str | None
    verdict: str            # "names_and_structure" | "structure" | "scan_needed" | "looks_empty"
    old_fat: bool           # the FAT still holds chains (exFAT)
    fat_links: int
    old_root: bool          # a root folder with real entries is still readable
    root_folders: list      # first-level folder names found in it
    root_files: int
    blank_fraction: float   # share of sampled blocks that are empty


def _blank(block):
    return not block.strip(b"\x00") or not block.strip(b"\xff")


def _sample_blank(disk):
    """Data is written from the start of a drive, so half the samples go to
    the first gigabyte: an emptied drive is blank there too."""
    near = min(disk.size, 1024 ** 3)
    spots = [near * i // 256 for i in range(8, 256)]
    spots += [near + (disk.size - near) * i // 256 for i in range(256)] if disk.size > near else []
    blocks = [disk.read(s - s % 512, SAMPLE) for s in spots]
    blocks = [b for b in blocks if b]
    return sum(1 for b in blocks if _blank(b)) / len(blocks) if blocks else 1.0


def _fat_links(disk, boot):
    """Entries that chain one cluster to another. A fresh exFAT has only the
    few that describe its own bitmap, upcase table and root."""
    raw = disk.read(boot["fat_off"], boot["fat_len"])
    n = min(len(raw) // 4, boot["nclus"] + 2)
    table = struct.unpack_from(f"<{n}I", raw)
    return sum(1 for i, x in enumerate(table) if 2 <= x < n and i > boot["root"])


def _old_root(disk):
    """Best root folder found near the start: (folder names, file count)."""
    best = ([], 0)
    for off in range(0, min(PROBE, disk.size), 8 * 1024 * 1024):
        buf = disk.read(off, 8 * 1024 * 1024 + 128)
        for p in find_exfat_roots(buf, min(len(buf), 8 * 1024 * 1024)):
            ents = parse_dir(disk.read(off + p, 128 * 1024), False)[0]
            ents = [en for en in ents if en.name.lower() not in SYSTEM_NAMES]
            folders = [en.name for en in ents if en.is_dir]
            files = sum(1 for en in ents if not en.is_dir)
            if len(folders) + files > len(best[0]) + best[1]:
                best = (folders, files)
    return best


def diagnose(disk):
    boot = read_boot(disk)
    fs = boot["fs"] if boot else None
    links = _fat_links(disk, boot) if fs == "exfat" else 0
    folders, files = _old_root(disk)
    blank = _sample_blank(disk)
    old_root = bool(folders or files)
    if old_root:
        verdict = "names_and_structure"
    elif links:
        verdict = "structure"
    elif blank >= 1.0:
        verdict = "looks_empty"
    else:
        verdict = "scan_needed"
    return Diagnosis(fs, verdict, bool(links), links, old_root, folders, files, blank)
