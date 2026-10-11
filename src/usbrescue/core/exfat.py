"""exFAT: parse folders, deduce the old geometry and rebuild the tree while
the scan is still running."""

import collections
import datetime

from .model import Entry, FolderFound, FolderPlaced, GeometryCalibrated, Geometry, RootRecovered
from .oldfat import EOC, load_old_fat
from .scan import EX_FILE, EX_STREAM
from .util import CLUSTER_SIZES, ENTRY, u16, u32, u64

EX_KNOWN = {0x81, 0x82, 0x83, 0xA0, 0xA1, 0xA2, 0x85, 0xC0, 0xC1}
DIR_FIRST_BYTES = (0x85, 0x05, 0x81, 0x82, 0x83, 0xC0, 0xC1, 0x40, 0x41)
CALIBRATION_STARTS = 4000   # folder blocks used to deduce the geometry
EARLY_MIN_REFS = 8          # references needed before trusting the boot sector early
# folders the operating system creates by itself on a freshly formatted drive
SYSTEM_NAMES = {"system volume information", "$recycle.bin"}


def ex_dt(ts):
    try:
        return datetime.datetime(1980 + (ts >> 25), (ts >> 21) & 0xF, (ts >> 16) & 0x1F,
                                 (ts >> 11) & 0x1F, (ts >> 5) & 0x3F, (ts & 0x1F) * 2)
    except ValueError:
        return None


def ex_checksum(es):
    chk = 0
    for i, b in enumerate(es):
        if i in (2, 3):
            continue
        chk = ((((chk & 1) << 15) | (chk >> 1)) + b) & 0xFFFF
    return chk


def parse_dir(raw, want_deleted):
    """Returns (entries, end_found, junk_found)."""
    out, p = [], 0
    n = len(raw)
    while p + ENTRY <= n:
        t = raw[p]
        if t == 0x00:
            return out, True, False
        deleted = not (t & 0x80)
        if (t | 0x80) not in EX_KNOWN:
            return out, False, True
        if (t | 0x80) != EX_FILE:
            p += ENTRY
            continue
        sec = raw[p + 1]
        end = p + ENTRY * (1 + sec)
        if sec < 2 or end > n:
            p += ENTRY
            continue
        es = raw[p:end]
        if (es[32] | 0x80) != EX_STREAM:
            p += ENTRY
            continue
        if deleted and not want_deleted:
            p = end
            continue
        if not deleted and ex_checksum(es) != u16(es, 2):
            p += ENTRY
            continue
        nlen = es[35]
        name = b"".join(es[64 + 32 * k + 2:64 + 32 * k + 32] for k in range(sec - 1))
        # nlen counts UTF-16 units, not characters (an emoji takes two)
        name = name[:nlen * 2].decode("utf-16-le", "replace")
        en = Entry()
        en.name = name if not deleted else "_" + name
        en.is_dir = bool(u16(es, 4) & 0x10)
        en.cluster = u32(es, 52)
        en.size = u64(es, 56)
        en.valid = u64(es, 40)
        en.contiguous = bool(es[33] & 0x02)
        en.mtime = ex_dt(u32(es, 12))
        en.deleted = deleted
        out.append(en)
        p = end
    return out, False, False


def _vote(refs, starts, sset):
    """Try every cluster size: the right (size, start) makes the folders that
    are referenced land on sectors where folders really are."""
    def score(cs, st):
        return sum(1 for x in refs if st + (x - 2) * cs in sset)

    sample = refs[:300]
    best = None
    for cs in CLUSTER_SIZES[3:]:   # 4 KB .. 32 MB
        votes = collections.Counter()
        for x in sample:
            base = (x - 2) * cs
            for s in starts:
                st = s - base
                if st >= 0:
                    votes[st] += 1
        if votes:
            st, _ = votes.most_common(1)[0]
            sc = score(cs, st)
            if best is None or sc > best[2]:
                best = (cs, st, sc, len(refs))
    return best


class ExfatTree:
    """Builds the folder tree as folder blocks arrive from the scan.

    Feed it with add_start() in disk order, call checkpoint() now and then and
    finish() at the end; all three yield events. Folders are read as soon as
    the geometry is known, so the tree grows during the scan."""

    def __init__(self, disk, boot, want_deleted):
        self.disk, self.boot, self.want_deleted = disk, boot, want_deleted
        self.starts, self.sset = [], set()
        self.roots = []             # sectors that look like the start of a root folder
        self.root_cluster = 0       # the root folder whose entries are used
        self.root_entries = []
        self.root_is_old = False    # ...and whether it is the one from before the format
        self.geometry = None
        self.calibration = (0, 0)
        self.contents, self.dir_cls, self.parent_of = {}, {}, {}
        self._known_len = {}
        self._names = {}        # name a parent gives each folder (live preview only)
        self._queue = []        # folders named by a parent but not seen as a block yet
        self._visited = 0       # how many starts have been handled
        self._refs = {}         # clusters of folders named inside the first blocks
        self._refs_upto = 0

    def add_start(self, off):
        self.starts.append(off)
        self.sset.add(off)

    def add_root(self, off):
        self.roots.append(off)

    # ------------------------------------------------------------ geometry

    def _collect_refs(self):
        upto = min(len(self.starts), CALIBRATION_STARTS)
        for s in self.starts[self._refs_upto:upto]:
            for en in parse_dir(self.disk.read(s, 4096), self.want_deleted)[0]:
                if en.is_dir and en.cluster >= 2:
                    self._refs[en.cluster] = True
        self._refs_upto = upto

    def _boot_is_exfat(self):
        return bool(self.boot) and self.boot["fs"] == "exfat"

    def _calibrate_early(self, scanned_end):
        """During the scan only the cheap test is possible: does the boot
        sector's geometry explain the folders seen so far?"""
        if not self._boot_is_exfat():
            return
        self._collect_refs()
        cs, st = self.boot["cs"], self.boot["start"]
        offs = [st + (x - 2) * cs for x in self._refs]
        seen = [o for o in offs if o < scanned_end]
        if len(seen) < EARLY_MIN_REFS:
            return
        if sum(1 for o in seen if o in self.sset) >= 0.6 * len(seen):
            self._set_geometry(cs, st)

    def _calibrate_final(self):
        self._collect_refs()
        refs = list(self._refs)
        if not refs:
            if self._boot_is_exfat():
                self._set_geometry(self.boot["cs"], self.boot["start"])
            return
        if self._boot_is_exfat():
            cs, st = self.boot["cs"], self.boot["start"]
            sc = sum(1 for x in refs if st + (x - 2) * cs in self.sset)
            if sc >= 0.6 * len(refs):
                self._set_geometry(cs, st)
                return
        best = _vote(refs, self.starts, self.sset)
        if best:
            self._set_geometry(best[0], best[1])

    def _set_geometry(self, cs, start):
        self.geometry = Geometry(cs, start)
        self.geometry.fat = load_old_fat(self.disk, self.boot, self.geometry)

    def _calibrated_event(self):
        g = self.geometry
        return GeometryCalibrated("exfat", g.cs, g.start, g.fat is not None)

    # ------------------------------------------------------------- reading

    def _read_dir(self, c, length=None, contiguous=True):
        if c in self.contents:
            return
        g, cs = self.geometry, self.geometry.cs
        raws, used = [], []
        nclus = max(1, (length + cs - 1) // cs) if length and contiguous else 4096
        clusters = range(c, c + nclus)
        if g.fat and length and not contiguous:
            # fragmented folder: follow its chain in the old FAT
            clusters = g.fat.chain(c, max(1, (length + cs - 1) // cs)) or clusters
        for k, cc in enumerate(clusters):
            raw = self.disk.read(g.coff(cc), cs)
            if not raw:
                break
            if k and length is None and g.coff(cc) not in self.sset and raw[0] not in DIR_FIRST_BYTES:
                break
            _, ended, junk = parse_dir(raw, self.want_deleted)
            raws.append(raw)
            used.append(cc)
            if ended or junk:
                break
        # parsed as one piece: an entry set may straddle two clusters
        self.contents[c] = parse_dir(b"".join(raws), self.want_deleted)[0]
        for u in used:
            self.dir_cls[u] = c

    def _read_root(self, c):
        """Entries of a root folder starting at cluster c, and its clusters.
        A root always uses the FAT; without one, assume it is contiguous."""
        g = self.geometry
        clusters = None
        if g.fat:
            chain, x = [], c
            while 2 <= x < g.fat.n and len(chain) < 4096 and x not in chain:
                chain.append(x)
                x = g.fat.t[x]
            if x == EOC:
                clusters = chain
        raws, used = [], []
        for k, cc in enumerate(clusters or range(c, c + 4096)):
            raw = self.disk.read(g.coff(cc), g.cs)
            if not raw or (k and raw[0] not in DIR_FIRST_BYTES):
                break
            _, ended, junk = parse_dir(raw, self.want_deleted)
            raws.append(raw)
            used.append(cc)
            if ended or junk:
                break
        return parse_dir(b"".join(raws), self.want_deleted)[0], used

    def _adopt_root(self):
        """Among the root-looking blocks, keep the one that names the most
        folders nobody else claims. The root written by the new format names
        none, so it never wins."""
        g = self.geometry
        best = (0, None, None, None)
        for off in self.roots:
            if off < g.start or (off - g.start) % g.cs:
                continue
            c = g.cluster_of(off)
            ents, used = self._read_root(c)
            score = sum(1 for en in ents if en.is_dir and en.cluster in self.contents
                        and en.cluster not in self.parent_of)
            if score > best[0]:
                best = (score, c, ents, used)
        score, c, ents, used = best
        if not score:
            return
        self.root_cluster, self.root_entries = c, ents
        for u in used:
            self.dir_cls[u] = c
        # the root written by the new format may name what the system added
        # afterwards; that is not the user's old root
        old = [en for en in ents if en.name.lower() not in SYSTEM_NAMES]
        self.root_is_old = bool(old)
        if old:
            yield RootRecovered(sum(1 for en in old if en.is_dir),
                                sum(1 for en in old if not en.is_dir))

    def _visit(self, c):
        if c in self.dir_cls:
            return
        length, contiguous = self._known_len.get(c, (None, True))
        self._read_dir(c, length, contiguous)
        ents = self.contents[c]
        files = [en for en in ents if not en.is_dir]
        yield FolderFound(c, self.parent_of.get(c), self._names.get(c),
                          len(files), sum(en.size for en in files))
        for en in ents:
            if en.is_dir and en.cluster >= 2:
                first = en.cluster not in self.parent_of
                self.parent_of.setdefault(en.cluster, c)
                self._known_len[en.cluster] = (en.size, en.contiguous)
                if first:
                    self._names[en.cluster] = en.name
                if en.cluster not in self.contents:
                    self._queue.append(en.cluster)
                elif first:
                    yield FolderPlaced(en.cluster, c, en.name)

    def _drain(self):
        g = self.geometry
        while self._visited < len(self.starts):
            s = self.starts[self._visited]
            self._visited += 1
            if s >= g.start and (s - g.start) % g.cs == 0:
                yield from self._visit(g.cluster_of(s))

    # -------------------------------------------------------------- public

    def checkpoint(self, scanned_end):
        if self.geometry is None:
            self._calibrate_early(scanned_end)
            if self.geometry is None:
                return
            yield self._calibrated_event()
        yield from self._drain()

    def finish(self):
        """Returns through events; afterwards self.geometry is None if the
        geometry could not be deduced."""
        if self.geometry is None:
            self._calibrate_final()
            if self.geometry is None:
                return
            yield self._calibrated_event()
        yield from self._drain()
        # folders named by a parent that never showed up as a block of their own
        i = 0
        while i < len(self._queue):
            yield from self._visit(self._queue[i])
            i += 1
        # read again, with the exact size, the folders whose size became known
        for c, (length, contiguous) in self._known_len.items():
            if c in self.contents:
                for u in [u for u, owner in self.dir_cls.items() if owner == c]:
                    del self.dir_cls[u]
                del self.contents[c]
                self._read_dir(c, length, contiguous)
        # blocks nobody points to are first-level folders: their names were in
        # the root, which the format wiped
        yield from self._adopt_root()
        top_names = {en.cluster: en.name for en in self.root_entries if en.is_dir}
        for c in list(self.contents):
            if c not in self.parent_of:
                self.parent_of[c] = 0
                yield FolderPlaced(c, 0, top_names.get(c))
        g = self.geometry
        self._collect_refs()
        refs = list(self._refs)
        self.calibration = (sum(1 for x in refs if g.coff(x) in self.sset), len(refs))
