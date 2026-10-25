"""A look that takes seconds, before the long scan: what did the format leave?

It reads the boot sector, the FAT, the start of the volume and a spread of
samples. Its answer is a forecast, not a promise: only the scan confirms it,
and it must never be used to turn someone away."""

import struct
from dataclasses import dataclass

from . import fat32, ntfs
from .boot import read_boot
from .exfat import SYSTEM_NAMES, parse_dir
from .scan import find_exfat_roots

PROBE = 64 * 1024 * 1024    # roots live near the start of a volume
SAMPLE = 4096


@dataclass
class Diagnosis:
    current_fs: str | None
    verdict: str            # "in_use" | "names_and_structure" | "structure" | "scan_needed"
                            # | "looks_empty"
    current_folders: list   # what the drive shows right now, as any computer sees it
    current_files: int
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


def _user_entries(ents):
    ents = [en for en in ents if en.name.lower() not in SYSTEM_NAMES]
    return [en.name for en in ents if en.is_dir], sum(1 for en in ents if not en.is_dir)


def _current_root(disk, boot):
    """What the file system on the drive shows today: (folder names, files).
    A drive that was just formatted shows nothing here."""
    if not boot:
        return [], 0
    if boot["fs"] == "ntfs":
        return _user_entries(_ntfs_root(disk, boot))
    cs, cluster, raws = boot["cs"], boot["root"], []
    offset = lambda c: boot["start"] + (c - 2) * cs
    if boot["fs"] == "exfat":
        seen = set()
        while 2 <= cluster < boot["nclus"] + 2 and cluster not in seen and len(seen) < 64:
            seen.add(cluster)
            raws.append(disk.read(offset(cluster), cs))
            nxt = disk.read(boot["fat_off"] + 4 * cluster, 4)
            cluster = struct.unpack("<I", nxt)[0] if len(nxt) == 4 else 0
        return _user_entries(parse_dir(b"".join(raws), False)[0])
    for k in range(8):                      # FAT32: the root is nearly always contiguous
        raw = disk.read(offset(cluster + k), cs)
        raws.append(raw)
        if not raw or fat32.parse_dir(raw, False)[1]:
            break
    return _user_entries(fat32.parse_dir(b"".join(raws), False)[0])


def _ntfs_root(disk, boot, most=4096):
    """Live files and folders at the top of today's NTFS volume (from the
    first records of its MFT: enough to tell whether it is in use)."""
    mft = ntfs.CurrentMft(disk, boot)
    out = []
    for start, first, n in mft.extents:
        n = min(n, most - first)
        raw = disk.read(start, n * mft.rs)
        for k in range(n):
            if first + k < ntfs.FIRST_USER:
                continue
            r = ntfs.parse_record(raw[k * mft.rs:(k + 1) * mft.rs], start + k * mft.rs)
            if r and not r.base and r.in_use and r.parent == ntfs.ROOT and r.name and mft.live(r):
                out.append(ntfs.entry_of(r, []))
        if first + n >= most:
            break
    return out


def _old_root(disk, skip):
    """Best root folder found near the start, other than the one at `skip`
    (the current one): (folder names, file count)."""
    best = ([], 0)
    for off in range(0, min(PROBE, disk.size), 8 * 1024 * 1024):
        buf = disk.read(off, 8 * 1024 * 1024 + 128)
        for p in find_exfat_roots(buf, min(len(buf), 8 * 1024 * 1024)):
            if off + p == skip:
                continue
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
    current_folders, current_files = _current_root(disk, boot)
    here = boot["start"] + (boot["root"] - 2) * boot["cs"] if boot and "root" in boot else -1
    folders, files = _old_root(disk, here)
    blank = _sample_blank(disk)
    old_root = bool(folders or files)
    if current_folders or current_files:
        verdict = "in_use"          # nothing is missing as far as the drive itself can tell
    elif old_root:
        verdict = "names_and_structure"
    elif links:
        verdict = "structure"
    elif blank >= 1.0:
        verdict = "looks_empty"
    else:
        verdict = "scan_needed"
    return Diagnosis(fs, verdict, current_folders, current_files, bool(links), links,
                     old_root, folders, files, blank)
