"""NTFS: files and folders from MFT records.

Every file and folder on NTFS has a record ("FILE", usually 1 KB) in the
Master File Table. A record holds the name, the folder it is in, the dates,
and where the content is (a list of cluster runs, or the content itself when
the file is tiny). A quick format writes a new, small MFT: the old records
past it, or elsewhere on the drive, survive. Since each record names its
parent folder, the tree comes back from the records alone."""

import bisect
import datetime
from collections import defaultdict

from .model import Entry, Geometry
from .util import u16, u32, u64

AT_SI, AT_FN, AT_DATA, AT_IALLOC, AT_BITMAP = 0x10, 0x30, 0x80, 0xA0, 0xB0
ROOT = 5                # record number of the root folder; also its id in the tree
EXTEND = 11             # $Extend: a system folder
FIRST_USER = 16         # records below this one belong to the file system itself
IN_USE, IS_DIR = 1, 2
REF = (1 << 48) - 1
COMPRESSED, ENCRYPTED, SPARSE = 0x0001, 0x4000, 0x8000

# what a file's first bytes look like, to check where a cluster number points
MAGIC = {".jpg": (0, b"\xff\xd8\xff"), ".jpeg": (0, b"\xff\xd8\xff"), ".png": (0, b"\x89PNG"),
         ".gif": (0, b"GIF8"), ".pdf": (0, b"%PDF"), ".zip": (0, b"PK\x03\x04"),
         ".docx": (0, b"PK\x03\x04"), ".xlsx": (0, b"PK\x03\x04"), ".pptx": (0, b"PK\x03\x04"),
         ".mp4": (4, b"ftyp"), ".mov": (4, b"ftyp"), ".m4a": (4, b"ftyp"), ".mp3": (0, b"ID3"),
         ".doc": (0, b"\xd0\xcf\x11\xe0"), ".xls": (0, b"\xd0\xcf\x11\xe0"),
         ".ppt": (0, b"\xd0\xcf\x11\xe0"), ".rar": (0, b"Rar!"), ".7z": (0, b"7z\xbc\xaf"),
         ".exe": (0, b"MZ"), ".wav": (0, b"RIFF"), ".avi": (0, b"RIFF")}


def filetime(ft):
    if not ft:
        return None
    try:
        return datetime.datetime.fromtimestamp((ft - 116444736000000000) / 1e7)
    except (OverflowError, OSError, ValueError):
        return None


def header_ok(b, p):
    """Does a sector-aligned "FILE" at b[p] start a record that makes sense?"""
    if b[p:p + 4] != b"FILE" or p + 0x30 > len(b):
        return False
    usa_off, usa_n = u16(b, p + 4), u16(b, p + 6)
    first, used, alloc = u16(b, p + 0x14), u32(b, p + 0x18), u32(b, p + 0x1C)
    return (alloc in (1024, 2048, 4096) and usa_n >= 2 and alloc % (usa_n - 1) == 0
            and alloc // (usa_n - 1) in (512, 1024, 2048, 4096)
            and 0x28 <= usa_off and usa_off + 2 * usa_n <= first < used <= alloc)


def fixup(raw):
    """The last two bytes of each sector of a record are kept in its update
    sequence array, and a check value is written in their place. A record
    whose check values don't match was torn while being written."""
    usa_off, n = u16(raw, 4), u16(raw, 6)
    stride = len(raw) // (n - 1)
    b = bytearray(raw)
    check = raw[usa_off:usa_off + 2]
    for i in range(1, n):
        end = i * stride - 2
        if b[end:end + 2] != check:
            return None
        b[end:end + 2] = raw[usa_off + 2 * i:usa_off + 2 * i + 2]
    return bytes(b)


def runlist(b, p, end):
    """[(first cluster, count)]; first is -1 for a run with nothing stored
    (a sparse hole, or the saved space of a compressed unit)."""
    runs, lcn = [], 0
    while p < end and b[p]:
        nl, no = b[p] & 15, b[p] >> 4
        p += 1
        if not nl or p + nl + no > end:
            return None
        count = int.from_bytes(b[p:p + nl], "little")
        p += nl
        if count <= 0:
            return None
        if no:
            lcn += int.from_bytes(b[p:p + no], "little", signed=True)
            p += no
            if lcn < 0:
                return None
            runs.append((lcn, count))
        else:
            runs.append((-1, count))
    return runs


class Rec:
    """What one MFT record says. pieces: the unnamed data stream, as
    (first vcn, runs, size, valid size, flags, compression unit, resident bytes)."""

    __slots__ = ("off", "recno", "seq", "flags", "base", "base_seq", "lsn", "name", "ns",
                 "parent", "pseq", "mtime", "pieces", "idx_runs", "bitmap")

    @property
    def in_use(self):
        return bool(self.flags & IN_USE)

    @property
    def is_dir(self):
        return bool(self.flags & IS_DIR)


def parse_record(raw, off):
    if not header_ok(raw, 0) or len(raw) < u32(raw, 0x1C):
        return None
    b = fixup(raw[:u32(raw, 0x1C)])
    if b is None:
        return None
    r = Rec()
    r.off, r.lsn, r.seq, r.flags = off, u64(b, 8), u16(b, 0x10), u16(b, 0x16)
    ref = u64(b, 0x20)
    r.base, r.base_seq = ref & REF, ref >> 48
    r.recno = u32(b, 0x2C) if u16(b, 4) >= 0x30 else None   # NTFS 3.1 keeps it here
    r.name = r.parent = r.pseq = r.mtime = r.idx_runs = r.bitmap = None
    r.ns, r.pieces = 9, []
    p, end = u16(b, 0x14), min(u32(b, 0x18), len(b))
    while p + 16 <= end:
        t, ln = u32(b, p), u32(b, p + 4)
        if t == 0xFFFFFFFF or ln < 16 or p + ln > end:
            break
        nonres, nlen, noff, aflags = b[p + 8], b[p + 9], u16(b, p + 10), u16(b, p + 12)
        aname = b[p + noff:p + noff + 2 * nlen].decode("utf-16-le", "replace") if nlen else ""
        if not nonres:
            vlen, voff = u32(b, p + 16), u16(b, p + 20)
            v = b[p + voff:p + voff + vlen]
            if len(v) < vlen:
                break
            if t == AT_SI and vlen >= 16:
                r.mtime = filetime(u64(v, 8))
            elif t == AT_FN and vlen >= 66:
                nl, ns = v[64], v[65]
                # a long name wins over its DOS 8.3 twin (namespace 2)
                if 66 + 2 * nl <= vlen and nl and (r.name is None or (r.ns == 2 and ns != 2)):
                    pref = u64(v, 0)
                    r.parent, r.pseq = pref & REF, pref >> 48
                    r.name, r.ns = v[66:66 + 2 * nl].decode("utf-16-le", "replace"), ns
                    if r.mtime is None:
                        r.mtime = filetime(u64(v, 16))
            elif t == AT_DATA and not nlen:
                r.pieces.append((0, None, vlen, vlen, aflags, 0, v))
            elif t == AT_BITMAP and not nlen:
                r.bitmap = v
        elif ln >= 64:
            svcn, roff, unit = u64(b, p + 16), u16(b, p + 32), u16(b, p + 34)
            runs = runlist(b, p + roff, p + ln)
            if runs is not None:
                size, valid = u64(b, p + 48), u64(b, p + 56)
                if t == AT_DATA and not nlen:
                    r.pieces.append((svcn, runs, size, valid, aflags, unit, None))
                elif t == AT_IALLOC and aname == "$I30" and svcn == 0:
                    r.idx_runs = runs
                elif t == AT_BITMAP and not nlen:
                    r.bitmap = (runs, size)
        p += ln
    return r


def read_stream(disk, part, cs, runs, size):
    out, left = bytearray(), size
    for lcn, count in runs:
        n = min(left, count * cs)
        out += b"\x00" * n if lcn < 0 else disk.read(part + lcn * cs, n)
        left -= n
        if left <= 0:
            break
    return bytes(out)


def _stream(disk, boot, r):
    """The unnamed data of a record of the current file system, whole."""
    if not r.pieces:
        return b""
    first = r.pieces[0]
    if first[6] is not None:
        return first[6]
    runs = [run for piece in sorted(r.pieces) for run in piece[1]]
    return read_stream(disk, boot["part"], boot["cs"], runs, first[2])


def mft_record(disk, boot, n):
    """Record n of the current file system (n < 16: those are never moved)."""
    off = boot["mft"] + n * boot["rec"]
    return parse_record(disk.read(off, boot["rec"]), off)


class CurrentMft:
    """The MFT of the file system on the drive now. A record found at its
    slot n with n marked in use in its bitmap is a live file of today's drive,
    not something to bring back."""

    def __init__(self, disk, boot):
        self.extents, self.bits, self.rs, self.count = [], b"", 0, 0
        if not boot or boot["fs"] != "ntfs":
            return
        r = mft_record(disk, boot, 0)
        if not r or not r.pieces or r.pieces[0][1] is None:
            return
        self.rs, cs, part = boot["rec"], boot["cs"], boot["part"]
        self.count = r.pieces[0][2] // self.rs
        vcn = 0
        for piece in sorted(r.pieces):
            for lcn, n in piece[1]:
                if lcn >= 0:
                    self.extents.append((part + lcn * cs, vcn * cs // self.rs, n * cs // self.rs))
                vcn += n
        if isinstance(r.bitmap, bytes):
            self.bits = r.bitmap
        elif r.bitmap:
            self.bits = read_stream(disk, part, cs, *r.bitmap)

    def slot(self, off):
        for start, first, n in self.extents:
            if start <= off < start + n * self.rs and (off - start) % self.rs == 0:
                k = first + (off - start) // self.rs
                return k if k < self.count else None
        return None

    def live(self, r):
        k = self.slot(r.off)
        return k is not None and k == r.recno and k >> 3 < len(self.bits) and self.bits[k >> 3] >> (k & 7) & 1


def _partitions(disk):
    """[(start, size)] of the MBR's partitions, in bytes."""
    mbr = disk.read(0, 512)
    out = []
    if len(mbr) == 512 and mbr[510:512] == b"\x55\xaa":
        for i in range(4):
            lba, count = u32(mbr, 446 + 16 * i + 8), u32(mbr, 446 + 16 * i + 12)
            if lba:
                out.append((lba * 512, count * 512))
    return out


def backup_boot(disk):
    """NTFS keeps a copy of its boot sector in the last sector of the volume,
    and a quick format to exFAT or FAT32 leaves it there: (cluster size,
    volume start) of the old NTFS, or None."""
    from .boot import _vbr
    ends = [disk.size] + [start + size for start, size in _partitions(disk)]
    for end in ends:
        if end < 1024 or end > disk.size:
            continue
        info = _vbr(disk, end - 512)
        if info and info["fs"] == "ntfs":
            sectors = u64(disk.read(end - 512, 512), 40)
            start = end - 512 - sectors * 512      # the copy sits right after the volume's sectors
            if start >= 0:
                return info["cs"], start
    return None


def calibrate(disk, boot, dirs, files):
    """Cluster size and where the old volume started. A folder's index
    blocks start with "INDX", and many files start with a known signature:
    the right geometry is the one where the most of them are found."""
    idx = [d.idx_runs[0][0] for d in dirs if d.idx_runs and d.idx_runs[0][0] >= 0][:96]
    sig = []
    for en in files:
        ext = en.name[en.name.rfind("."):].lower() if "." in en.name else ""
        if ext in MAGIC and en.runs and en.runs[0][0] >= 0 and not en.compressed:
            sig.append((en.runs[0][0],) + MAGIC[ext])
            if len(sig) >= 96:
                break
    preferred = (boot["cs"], boot["part"]) if boot and boot["fs"] == "ntfs" else backup_boot(disk)
    parts = {start for start, _ in _partitions(disk)}
    starts = {0, 63 * 512, 2048 * 512} | parts
    if preferred:
        starts.add(preferred[1])
    best = None
    for cs in (512 << k for k in range(8)):
        for part in sorted(starts):
            hits = sum(disk.read(part + lcn * cs, 4) == b"INDX" for lcn in idx)
            hits += sum(disk.read(part + lcn * cs + at, len(m)) == m for lcn, at, m in sig)
            key = (hits, (cs, part) == preferred, part in parts, cs == 4096)
            if best is None or key > best[0]:
                best = (key, cs, part)
    return best[1], best[2], (best[0][0], len(idx) + len(sig))


def entry_of(r, pieces):
    en = Entry()
    en.name, en.is_dir, en.mtime, en.deleted = r.name, r.is_dir, r.mtime, not r.in_use
    if en.is_dir:
        en.cluster, en.size = r.off, 0
        return en
    en.cluster, en.size = 0, 0
    pieces = sorted(pieces, key=lambda x: x[0])
    if not pieces:
        return en
    first = pieces[0]
    if first[6] is not None:
        en.data, en.size = first[6], len(first[6])
        return en
    if first[0] != 0:
        return en                   # the record with the start of the runs is gone
    runs, vcn = [], 0
    for svcn, rr, *_ in pieces:
        if rr is None or svcn != vcn:
            break
        runs += rr
        vcn += sum(n for _, n in rr)
    en.runs, en.size, en.valid = runs, first[2], first[3]
    stored = [lcn for lcn, _ in runs if lcn >= 0]
    en.cluster = stored[0] if stored else 0
    en.contiguous = len(stored) <= 1
    if first[4] & COMPRESSED:
        en.compressed = 1 << first[5]
    en.encrypted = bool(first[4] & ENCRYPTED)
    return en


class NtfsTree:
    """Collects MFT records during the scan, then builds the tree.
    deleted: False (what was there before the format), True (that and what
    had been deleted) or "only" (just deleted files, for a drive in use)."""

    def __init__(self, disk, boot, deleted):
        self.disk, self.boot, self.deleted = disk, boot, deleted
        self.recs = []
        self._current = None

    def add(self, raw, off):
        r = parse_record(raw, off)
        if r is not None and r.recno is not None and r.recno >= FIRST_USER:
            self.recs.append(r)

    @property
    def current(self):
        if self._current is None:
            self._current = CurrentMft(self.disk, self.boot)
        return self._current

    def _wanted_files(self, recs=None):
        live = self.current.live
        out = []
        for r in self.recs if recs is None else recs:
            if r.base or r.is_dir or r.name is None or r.parent == EXTEND or live(r):
                continue
            if r.in_use or self.deleted:
                out.append(r)
        # the same record seen twice (a copy at the same place in another MFT)
        seen, unique = set(), []
        for r in sorted(out, key=lambda r: -r.lsn):
            key = (r.recno, r.seq, r.parent, r.name)
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    def count(self):
        """How much this drive's old NTFS holds: (folders, files)."""
        files = self._wanted_files()
        parents = {r.parent for r in files}
        return len(parents - {ROOT}), len(files)

    @staticmethod
    def _index(recs):
        dirs, ext = defaultdict(list), defaultdict(list)
        for r in recs:
            if r.base:
                ext[(r.base, r.base_seq)].append(r)
            elif r.is_dir and r.name is not None:
                dirs[r.recno].append(r)
        return dirs, ext

    def _inside_files(self, recs, pieces_of, cs, part):
        """Offsets of records that lie inside the content of a file of the
        same drive. Files of today's drive are the holders when looking for
        deleted files; otherwise, files of the old one."""
        live = self.current.live
        spans = []
        for r in recs:
            if r.base or r.is_dir or not r.in_use or r.name is None:
                continue
            if live(r) != (self.deleted == "only"):
                continue
            for lcn, n in entry_of(r, pieces_of(r)).runs or ():
                if lcn >= 0:
                    spans.append((part + lcn * cs, part + (lcn + n) * cs))
        if not spans:
            return set()
        spans.sort()
        starts, ends = [], []
        for a, b in spans:
            if ends and a <= ends[-1]:
                ends[-1] = max(ends[-1], b)
            else:
                starts.append(a)
                ends.append(b)
        out = set()
        for r in recs:
            i = bisect.bisect_right(starts, r.off) - 1
            if i >= 0 and r.off < ends[i]:
                out.add(r.off)
        return out

    def build(self, names):
        """Returns (geometry, parent_of, contents, root_ents, dir_clusters,
        calibration, own names, labels)."""
        recs = self.recs
        dirs, ext = self._index(recs)

        def pieces_of(r):
            got = {p[0]: (0, p) for p in r.pieces}
            # deleting a file moves its sequence number up, but not the
            # base reference in its extension records
            others = ext.get((r.recno, r.seq), [])
            if not r.in_use:
                others = others + ext.get((r.recno, r.seq - 1), [])
            for e in others:
                for p in e.pieces:
                    d = abs(e.off - r.off)
                    if p[0] not in got or d < got[p[0]][0]:
                        got[p[0]] = (d, p)
            return [p for _, p in got.values()]

        def parent_rec(r):
            """The record of r's folder: ROOT, a dir Rec, or None if it is gone.
            A folder deleted with its files has its sequence number one up."""
            if r.parent == ROOT:
                return ROOT
            cands = [d for d in dirs.get(r.parent, ())
                     if d is not r and (d.seq == r.pseq or (not d.in_use and d.seq == r.pseq + 1))]
            return min(cands, key=lambda d: abs(d.off - r.off)) if cands else None

        files = self._wanted_files(recs)
        entries = [entry_of(r, pieces_of(r)) for r in files]
        all_dirs = [d for group in dirs.values() for d in group]
        cs, part, calibration = calibrate(self.disk, self.boot, all_dirs, entries)

        # records inside a file's data are not this drive's: a disk image
        # kept on it holds a whole MFT of its own
        inside = self._inside_files(recs, pieces_of, cs, part)
        if inside:
            recs = [r for r in recs if r.off not in inside]
            dirs, ext = self._index(recs)
            files = self._wanted_files(recs)
            entries = [entry_of(r, pieces_of(r)) for r in files]
            all_dirs = [d for group in dirs.values() for d in group]

        contents, parent_of, own, labels, root_ents = {}, {}, {}, {}, []

        def place(r):
            """Id of the folder r goes in (making that folder known)."""
            p = parent_rec(r)
            if p == ROOT:
                return ROOT
            if p is None:
                lost = -r.parent                # a folder whose record is gone
                if lost not in contents:
                    contents[lost], parent_of[lost] = [], 0
                    labels[lost] = names.unnamed_folder.format(r.parent)
                return lost
            add_dir(p)
            return p.off

        def add_dir(d):
            if d.off in contents:           # also ends a loop of parents
                return
            contents[d.off], own[d.off] = [], d.name
            pid = place(d)
            parent_of[d.off] = pid
            en = entry_of(d, [])
            (root_ents if pid == ROOT else contents[pid]).append(en)

        if self.deleted != "only":          # keep the folders, empty ones too
            live = self.current.live
            for group in dirs.values():
                for d in group:
                    if d.recno >= FIRST_USER and d.parent != EXTEND and not live(d) and \
                            (d.in_use or self.deleted):
                        add_dir(d)
        for r, en in zip(files, entries):
            pid = place(r)
            (root_ents if pid == ROOT else contents[pid]).append(en)

        g = Geometry(cs, part + 2 * cs)     # so that g.coff(lcn) = part + lcn * cs
        dir_cls = {}
        for r in recs:                      # the old MFT and folder indexes are no one's files
            dir_cls[g.cluster_of(r.off)] = 0
        for d in all_dirs:
            for lcn, n in d.idx_runs or ():
                for c in range(lcn, lcn + min(n, 4096)) if lcn >= 0 else ():
                    dir_cls[c] = d.off
        return g, parent_of, contents, root_ents, dir_cls, calibration, own, labels


# ------------------------------------------------------------ compression

def lznt1(buf, limit):
    """Windows' NTFS compression: chunks of up to 4 KB, each with a header;
    inside, groups of 8 items are literals or back references."""
    out, p = bytearray(), 0
    while p + 2 <= len(buf) and len(out) < limit:
        h = u16(buf, p)
        p += 2
        if not h:
            break
        chunk = buf[p:p + (h & 0xFFF) + 1]
        p += (h & 0xFFF) + 1
        if not h & 0x8000:
            out += chunk
            continue
        start, q = len(out), 0
        while q < len(chunk):
            flags = chunk[q]
            q += 1
            for bit in range(8):
                if q >= len(chunk):
                    break
                if not flags >> bit & 1:
                    out.append(chunk[q])
                    q += 1
                    continue
                if q + 2 > len(chunk):
                    q = len(chunk)
                    break
                t = u16(chunk, q)
                q += 2
                lbits, k = 12, len(out) - start - 1
                while k >= 0x10:
                    k >>= 1
                    lbits -= 1
                back = (t >> lbits) + 1
                if back > len(out) - start:
                    return bytes(out)       # damaged
                for _ in range((t & ((1 << lbits) - 1)) + 3):
                    out.append(out[-back])
    return bytes(out)


def iter_compressed(disk, g, runs, nbytes, unit):
    """A compressed file, unit by unit (usually 16 clusters): a unit with
    every cluster stored is plain, one with some stored is compressed, and
    one with none is zeros."""
    vcns = []
    for lcn, n in runs:
        vcns += [lcn] * n if lcn < 0 else range(lcn, lcn + n)
    left = nbytes
    for u in range(0, len(vcns), unit):
        part = vcns[u:u + unit]
        size = min(left, unit * g.cs)
        stored = [c for c in part if c >= 0]
        if len(stored) == len(part):
            data = b"".join(disk.read(g.coff(c), g.cs) for c in part)
        elif stored:
            data = lznt1(b"".join(disk.read(g.coff(c), g.cs) for c in stored), unit * g.cs)
        else:
            data = b""
        data = data[:size].ljust(size, b"\x00")
        yield data
        left -= size
        if left <= 0:
            return
