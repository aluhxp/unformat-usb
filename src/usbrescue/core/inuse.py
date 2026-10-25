"""Which clusters the drive's current file system uses right now.

A deleted file whose clusters are in use again was written over by a newer
file: its content is now someone else's. Only meaningful when the current
file system has the same geometry as the one the file came from."""

import struct

from .util import u32


class InUse:
    def __init__(self, used, nclus):
        self.used, self.nclus = used, nclus     # used(c) -> bool

    def mark(self, claimed):
        """Sets claimed[c] for every cluster in use."""
        for c in range(2, min(self.nclus + 2, len(claimed))):
            if self.used(c):
                claimed[c] = 1

    def any(self, runs):
        for first, count in runs:
            for c in range(first, first + count):
                if 2 <= c < self.nclus + 2 and self.used(c):
                    return True
        return False


def _exfat_bitmap(disk, boot, g):
    root = disk.read(g.coff(boot["root"]), g.cs)
    for p in range(0, len(root) - 31, 32):
        e = root[p:p + 32]
        if e[0] == 0:
            break
        if e[0] == 0x81:                    # allocation bitmap
            first = u32(e, 20)
            length = struct.unpack_from("<Q", e, 24)[0]
            bits = disk.read(g.coff(first), min(length, (boot["nclus"] + 7) // 8))
            if not bits:
                return None

            def used(c):
                i = c - 2
                return i >> 3 < len(bits) and bits[i >> 3] >> (i & 7) & 1

            return InUse(used, boot["nclus"])
    return None


def _fat32_table(disk, boot, g):
    raw = disk.read(boot["fat_off"], boot["fat_len"])
    n = len(raw) // 4
    table = memoryview(raw[:n * 4]).cast("I")

    def used(c):
        return c < n and table[c] & 0x0FFFFFFF != 0

    return InUse(used, n - 2)


def clusters_in_use(disk, boot, g):
    """An InUse, or None when the current file system can't tell."""
    if not boot or (boot["cs"], boot["start"]) != (g.cs, g.start):
        return None
    try:
        if boot["fs"] == "exfat":
            return _exfat_bitmap(disk, boot, g)
        if boot["fs"] == "fat32" and boot.get("fat_len"):
            return _fat32_table(disk, boot, g)
    except (OSError, ValueError, struct.error):
        return None
    return None
