"""The FAT table from before the format (exFAT).

A quick format rewrites only the first FAT entries. The rest still holds the
chains of fragmented files (contiguous files do not use the FAT in exFAT), so
those files can be rebuilt without guessing."""

import struct

EOC = 0xFFFFFFFF


class OldFat:
    def __init__(self, raw, nclus):
        self.n = min(len(raw) // 4, nclus + 2)
        self.t = struct.unpack_from(f"<{self.n}I", raw)

    def chain(self, c, need):
        """Clusters of the chain starting at c, or None unless it is exactly
        `need` clusters long and ends with end-of-chain."""
        out = []
        while len(out) < need:
            if not 2 <= c < self.n:
                return None
            out.append(c)
            c = self.t[c]
        return out if c == EOC else None

    def free_chain(self, c, claimed):
        """Whole chain from c that never steps on a known file's clusters."""
        out, seen = [], set()
        while c != EOC:
            if not 2 <= c < self.n or c >= len(claimed) or claimed[c] or c in seen:
                return None
            out.append(c)
            seen.add(c)
            c = self.t[c]
        return out


def load_old_fat(disk, boot, g):
    """Only trustworthy when the new format used the same geometry as the old
    one: then the FAT is still in the same place. Callers must check it against
    the known fragmented files before relying on it."""
    if not boot or boot["fs"] != "exfat" or (boot["cs"], boot["start"]) != (g.cs, g.start):
        return None
    raw = disk.read(boot["fat_off"], boot["fat_len"])
    fat = OldFat(raw, boot["nclus"])
    return fat if any(fat.t[2:]) else None


def to_runs(clusters):
    """[5, 6, 7, 20, 21] -> [(5, 3), (20, 2)]"""
    runs = []
    for c in clusters:
        if runs and runs[-1][0] + runs[-1][1] == c:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    return [tuple(r) for r in runs]
