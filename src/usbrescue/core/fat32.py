"""FAT32: parse folders, deduce the old geometry and rebuild the tree."""

import collections
import datetime

from .model import Entry, Geometry
from .scan import ATTR_DIR, ATTR_LFN, ATTR_VOL, DOT, DOTDOT, plausible_sfn
from .util import CLUSTER_SIZES, ENTRY, u16, u32


def fat_dt(date, tm):
    try:
        return datetime.datetime(1980 + (date >> 9), (date >> 5) & 0xF, date & 0x1F,
                                 tm >> 11, (tm >> 5) & 0x3F, (tm & 0x1F) * 2)
    except ValueError:
        return None


def sfn_checksum(raw11):
    s = 0
    for b in raw11:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def short_name(raw11, nt):
    base = raw11[:8].decode("cp850", "replace").rstrip()
    ext = raw11[8:11].decode("cp850", "replace").rstrip()
    if nt & 0x08:
        base = base.lower()
    if nt & 0x10:
        ext = ext.lower()
    if base.startswith("\x05"):
        base = "\xe5" + base[1:]
    return f"{base}.{ext}" if ext else base


def parse_dir(raw, want_deleted):
    """Returns (entries, end_found, junk_found)."""
    out, lfn, lfn_sum = [], {}, None
    for p in range(0, len(raw) - ENTRY + 1, ENTRY):
        e = raw[p:p + ENTRY]
        first, attr = e[0], e[11]
        if first == 0x00:
            return out, True, False
        deleted = first == 0xE5
        if attr == ATTR_LFN:
            part = (e[1:11] + e[14:26] + e[28:32]).decode("utf-16-le", "replace")
            part = part.split("\x00")[0].replace("￿", "")
            if deleted:
                lfn[-len(lfn) - 1] = part   # approximate order
            else:
                if first & 0x40:
                    lfn = {}
                lfn[first & 0x1F] = part
            lfn_sum = e[13]
            continue
        if not deleted and not plausible_sfn(e):
            return out, False, True
        if attr & ATTR_VOL or e[:11] in (DOT[:11], DOTDOT[:11]) or (deleted and not want_deleted):
            lfn = {}
            continue
        name = None
        if lfn and (deleted or lfn_sum == sfn_checksum(e[:11])):
            keys = sorted(lfn, reverse=deleted) if deleted else sorted(lfn)
            name = "".join(lfn[k] for k in keys)
        if not name:
            name = short_name(e[:11], e[12])
            if deleted:
                name = "_" + name[1:]
        lfn = {}
        en = Entry()
        en.name = name
        en.is_dir = bool(attr & ATTR_DIR)
        en.cluster = u16(e, 20) << 16 | u16(e, 26)
        en.size = u32(e, 28)
        en.mtime = fat_dt(u16(e, 24), u16(e, 22))
        en.deleted = deleted
        out.append(en)
    return out, False, False


def calibrate(dots, boot):
    cands = list(CLUSTER_SIZES)
    if boot and boot["fs"] == "fat32":
        cands.insert(0, boot["cs"])
    best = None
    for cs in dict.fromkeys(cands):
        votes = collections.Counter(o - (c - 2) * cs for o, c, _ in dots)
        start, hits = votes.most_common(1)[0]
        if start >= 0 and (best is None or hits > best[2]):
            best = (cs, start, hits)
    return best


def build_tree(disk, dots, refs, boot, want_deleted):
    """Returns (geometry, parent_of, contents, root_entries, dir_clusters,
    root_cluster, (hits, folders))."""
    cs, start, hits = calibrate(dots, boot)
    g = Geometry(cs, start)
    parent_of = {own: par for o, own, par in dots if o == g.coff(own)}
    root_cl = boot["root"] if boot and boot["fs"] == "fat32" else 2

    contents, dir_cls = {}, {}
    for c in parent_of:
        ents, used = [], []
        for k in range(4096):   # contiguous folder; stops at the first thing that is not one
            raw = disk.read(g.coff(c + k), cs)
            if not raw:
                break
            if k and (raw[:12] == DOT or raw[0] == 0 or not (plausible_sfn(raw[:32]) or raw[11] == ATTR_LFN)):
                break
            got, ended, junk = parse_dir(raw, want_deleted)
            ents += got
            used.append(c + k)
            if ended or junk:
                break
        contents[c] = ents
        for u in used:
            dir_cls[u] = c

    # what is left of the old root may still name first-level folders
    root_ents, frags = {}, set()
    for off, cl in refs:
        if parent_of.get(cl, -1) in (0, root_cl):
            fr = g.cluster_of(off)
            if fr >= 2 and fr not in dir_cls:
                frags.add(fr)
    for fr in sorted(frags):
        for en in parse_dir(disk.read(g.coff(fr), cs), want_deleted)[0]:
            root_ents[(en.name, en.cluster)] = en
    return g, parent_of, contents, list(root_ents.values()), dir_cls, root_cl, (hits, len(dots))
