"""Builds small NTFS test images without mounting anything or needing
Windows: the boot sector, the MFT with the file system's own records, the
cluster bitmap, and folders and files as real MFT records (names, parent
folders, dates, resident or non-resident data, fragments, sparse runs,
compression, extension records).

Only what a recovery reads is written: folder indexes hold just an "INDX"
header, so Windows would want to repair this volume, but every record is
laid out as NTFS lays it out.

quick_format() replays what the real mkntfs -Q wrote over a volume of this
geometry (see recorded.py), so the "format" is the real one."""

import datetime
import os
import struct

from . import recorded

SECTOR = 512
REC = 1024
MFT_LCN = 4
FIRST_USER = 64                 # where mkntfs starts handing out records
MFT_RECORDS = 1024
# areas the real mkntfs -Q writes on a 64 MB volume with 4 KB clusters
FORMAT_WRITES = [(0, 3), (4, 11), (2051, 2153), (8191, 8704), (16383, 16384)]
WHEN = datetime.datetime(2022, 5, 17, 9, 30)


def filetime(dt):
    return int((dt.timestamp() + 11644473600) * 10_000_000)


def encode_runs(runs):
    out, prev = bytearray(), 0
    for lcn, count in runs:
        nl = (count.bit_length() + 8) // 8
        cb = count.to_bytes(nl, "little")
        if lcn < 0:
            out += bytes([nl]) + cb
            continue
        delta = lcn - prev
        no = 1
        while not -(1 << (8 * no - 1)) <= delta < (1 << (8 * no - 1)):
            no += 1
        out += bytes([no << 4 | nl]) + cb + delta.to_bytes(no, "little", signed=True)
        prev = lcn
    return bytes(out) + b"\x00"


def _pad8(b):
    return b + b"\x00" * (-len(b) % 8)


def attr_res(kind, value, name="", ident=0):
    nm = name.encode("utf-16-le")
    voff = (24 + len(nm) + 7) // 8 * 8
    body = struct.pack("<IIBBHHHIHBB", kind, 0, 0, len(name), 24, 0, ident, len(value), voff, 0, 0)
    body = _pad8(body + nm)[:voff].ljust(voff, b"\x00") + value
    body = _pad8(body)
    return body[:4] + struct.pack("<I", len(body)) + body[8:]


def attr_nonres(kind, runs, size, valid=None, flags=0, unit=0, svcn=0, cs=4096, name="", ident=0):
    nm = name.encode("utf-16-le")
    roff = (64 + len(nm) + 7) // 8 * 8
    nvcn = sum(n for _, n in runs)
    rl = encode_runs(runs)
    head = struct.pack("<IIBBHHH", kind, 0, 1, len(name), 64, flags, ident)
    head += struct.pack("<QQHH4xQQQ", svcn, svcn + nvcn - 1, roff, unit,
                        nvcn * cs if svcn == 0 else 0, size if svcn == 0 else 0,
                        (size if valid is None else valid) if svcn == 0 else 0)
    body = _pad8((head + nm).ljust(roff, b"\x00") + rl)
    return body[:4] + struct.pack("<I", len(body)) + body[8:]


def si_value(when=WHEN):
    ft = filetime(when)
    return struct.pack("<QQQQI", ft, ft, ft, ft, 0x20).ljust(48, b"\x00")


def fn_value(parent, pseq, name, size=0, is_dir=False, ns=1, when=WHEN):
    ft = filetime(when)
    nm = name.encode("utf-16-le")
    return (struct.pack("<QQQQQQQII", parent | pseq << 48, ft, ft, ft, ft, size, size,
                        0x10000000 if is_dir else 0x20, 0)
            + bytes([len(name), ns]) + nm)


def record(recno, seq, flags, attrs, base=(0, 0), lsn=1000):
    usa_n = REC // SECTOR + 1
    first = (0x30 + 2 * usa_n + 7) // 8 * 8
    body = b"".join(attrs) + b"\xff\xff\xff\xff" + b"\x00" * 4
    used = first + len(body)
    assert used <= REC, "record too full"
    head = struct.pack("<4sHHQHHHHIIQHHI", b"FILE", 0x30, usa_n, lsn, seq, 1, first, flags,
                       used, REC, base[0] | base[1] << 48, len(attrs) + 1, 0, recno)
    rec = bytearray(head.ljust(first, b"\x00") + body)
    rec = rec.ljust(REC, b"\x00")
    usn = struct.pack("<H", 1)
    for i in range(1, usa_n):
        end = i * SECTOR - 2
        rec[0x30 + 2 * i:0x30 + 2 * i + 2] = rec[end:end + 2]
        rec[end:end + 2] = usn
    rec[0x30:0x32] = usn
    return bytes(rec)


def lznt1_compress(data):
    """A plain LZNT1 encoder (greedy, short search): enough to make test data."""
    out = bytearray()
    for c in range(0, len(data), 4096):
        chunk, body, i = data[c:c + 4096], bytearray(), 0
        while i < len(chunk):
            at, flags = len(body), 0
            body.append(0)
            for bit in range(8):
                if i >= len(chunk):
                    break
                lbits, k = 12, i - 1
                while k >= 0x10:
                    k >>= 1
                    lbits -= 1
                most = (1 << lbits) + 2
                best, back_at = 0, 0
                for back in range(1, min(i, 1 << (16 - lbits), 64) + 1):
                    n = 0
                    while n < most and i + n < len(chunk) and chunk[i + n - back] == chunk[i + n]:
                        n += 1
                    if n > best:
                        best, back_at = n, back
                if best >= 3:
                    body += struct.pack("<H", (back_at - 1) << lbits | (best - 3))
                    flags |= 1 << bit
                    i += best
                else:
                    body.append(chunk[i])
                    i += 1
            body[at] = flags
        if len(body) >= len(chunk):         # it doesn't shrink: kept as it is
            out += struct.pack("<H", 0x3000 | (len(chunk) - 1)) + chunk
        else:
            out += struct.pack("<H", 0xB000 | (len(body) - 1)) + body
    return bytes(out)


class _Node:
    def __init__(self, recno, parent, name, is_dir):
        self.recno, self.parent, self.name, self.is_dir = recno, parent, name, is_dir
        self.seq, self.flags = 1, 1 | (2 if is_dir else 0)
        self.children = {}
        self.data = b""
        self.runs = []          # clusters of the content (or of the index, for a folder)
        self.options = {}


class NtfsImage:
    """add() folders and files, then flush(); delete()/reuse() afterwards."""

    def __init__(self, path, size_mb=64, cs=4096, offset=0):
        self.path, self.cs, self.part = path, cs, offset
        self.size = size_mb * 1024 * 1024
        with open(path, "ab") as f:
            f.truncate(self.size)
        self.f = open(path, "r+b")
        self.nclus = (self.size - offset) // cs
        self.root = _Node(5, 5, ".", True)
        self.next_rec = FIRST_USER
        self.used = bytearray(self.nclus)
        for a, b in [(0, 3), (MFT_LCN, MFT_LCN + MFT_RECORDS * REC // cs)] + FORMAT_WRITES:
            for c in range(a, min(b, self.nclus)):
                self.used[c] = 1
        self.nodes = {5: self.root}

    # ------------------------------------------------------------ layout

    def _alloc(self, n, gap=0):
        """n free clusters in a row, the first free run after `gap` free ones."""
        c, skipped = 300, 0
        while c + n <= self.nclus:
            if any(self.used[c:c + n]):
                c += 1
                continue
            if skipped < gap:
                skipped += 1
                c += 1
                continue
            for k in range(c, c + n):
                self.used[k] = 1
            return c
        raise RuntimeError("image full")

    def _node(self, path):
        node = self.root
        for part in path.split("/"):
            node = node.children[part]
        return node

    def add(self, path, data=None, *, fragments=1, sparse=False, compressed=False,
            extension=False, when=WHEN):
        """A file (data given) or a folder (data None), with any folders above it."""
        parts = path.split("/")
        node = self.root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if part not in node.children:
                child = _Node(self.next_rec, node.recno, part, not (last and data is not None))
                self.next_rec += 1
                node.children[part] = child
                self.nodes[child.recno] = child
                if child.is_dir:
                    child.runs = [(self._alloc(1), 1)]
            node = node.children[part]
        if data is not None:
            node.data, node.when = data, when
            node.options = dict(fragments=fragments, sparse=sparse, compressed=compressed,
                                extension=extension)
            if len(data) > 600 or sparse or compressed or fragments > 1:
                self._place(node)
        return node

    def _place(self, node):
        data, cs, o = node.data, self.cs, node.options
        ncl = max(1, (len(data) + cs - 1) // cs)
        if o["compressed"]:
            node.runs, node.stored = [], []
            for u in range(0, ncl, 16):
                unit = data[u * cs:(u + 16) * cs]
                packed = lznt1_compress(unit)
                if len(unit) == 16 * cs and len(packed) <= 15 * cs:
                    k = (len(packed) + cs - 1) // cs
                    c = self._alloc(k)
                    node.runs += [(c, k), (-1, 16 - k)]
                    node.stored.append((c, packed))
                else:
                    k = (len(unit) + cs - 1) // cs
                    c = self._alloc(k)
                    node.runs.append((c, k))
                    node.stored.append((c, unit))
            return
        if o["sparse"]:
            # first cluster stored, then a hole of two clusters, then the rest
            assert ncl >= 4 and data[cs:3 * cs] == b"\x00" * 2 * cs
            a = self._alloc(1)
            b = self._alloc(ncl - 3)
            node.runs = [(a, 1), (-1, 2), (b, ncl - 3)]
            node.stored = [(a, data[:cs]), (b, data[3 * cs:])]
            return
        k = o["fragments"]
        sizes = [ncl // k + (1 if i < ncl % k else 0) for i in range(k)]
        node.runs, node.stored, at = [], [], 0
        for n in sizes:
            c = self._alloc(n, gap=2 if node.runs else 0)
            node.runs.append((c, n))
            node.stored.append((c, data[at * cs:(at + n) * cs]))
            at += n

    def _write(self, off, data):
        self.f.seek(off)
        self.f.write(data)

    def _rec_off(self, recno):
        return self.part + MFT_LCN * self.cs + recno * REC

    def _records_of(self, node):
        """[(record number, bytes)] for a node: one record, or a base and an
        extension record when its runs are split."""
        when = getattr(node, "when", WHEN)
        if node is self.root:
            attrs = [attr_res(0x10, si_value()), attr_res(0x30, fn_value(5, 5, ".", is_dir=True)),
                     attr_res(0x90, b"\x00" * 48, "$I30")]
            return [(5, record(5, 5, 3, attrs))]
        parent = self.nodes[node.parent]
        pseq = 5 if parent is self.root else parent.seq
        attrs = [attr_res(0x10, si_value(when)),
                 attr_res(0x30, fn_value(node.parent, pseq, node.name, len(node.data), node.is_dir))]
        if node.is_dir:
            attrs += [attr_res(0x90, b"\x00" * 48, "$I30"),
                      attr_nonres(0xA0, node.runs, self.cs, cs=self.cs, name="$I30")]
            return [(node.recno, record(node.recno, node.seq, node.flags, attrs))]
        o = node.options
        if not node.runs:
            attrs.append(attr_res(0x80, node.data))
            return [(node.recno, record(node.recno, node.seq, node.flags, attrs))]
        flags = (0x0001 if o["compressed"] else 0) | (0x8000 if o["sparse"] else 0)
        unit = 4 if o["compressed"] else 0
        if not o["extension"]:
            attrs.append(attr_nonres(0x80, node.runs, len(node.data), flags=flags, unit=unit, cs=self.cs))
            return [(node.recno, record(node.recno, node.seq, node.flags, attrs))]
        half = len(node.runs) // 2
        first, rest = node.runs[:half], node.runs[half:]
        attrs.append(attr_res(0x20, b"\x00" * 32))          # the attribute list (not read)
        attrs.append(attr_nonres(0x80, first, len(node.data), flags=flags, unit=unit, cs=self.cs))
        ext = self.next_rec
        self.next_rec += 1
        svcn = sum(n for _, n in first)
        ext_attrs = [attr_nonres(0x80, rest, len(node.data), flags=flags, unit=unit, svcn=svcn, cs=self.cs)]
        node.ext = ext
        return [(node.recno, record(node.recno, node.seq, node.flags, attrs)),
                (ext, record(ext, 1, 1, ext_attrs, base=(node.recno, node.seq)))]

    def volume_sectors(self):
        """Like mkntfs: every sector of the partition but the last, which
        holds the backup boot sector."""
        return (self.size - self.part) // SECTOR - 1

    def _boot(self, mft_lcn=MFT_LCN):
        b = bytearray(SECTOR)
        b[0:3] = b"\xeb\x52\x90"
        b[3:11] = b"NTFS    "
        struct.pack_into("<HB", b, 11, SECTOR, self.cs // SECTOR)
        b[21] = 0xF8
        struct.pack_into("<QQQ", b, 40, self.volume_sectors(), mft_lcn, self.nclus // 2)
        struct.pack_into("<bxxxbxxx", b, 64, -10, 1)
        b[510:512] = b"\x55\xaa"
        return bytes(b)

    def _system(self):
        """Records 0-15, the MFT bitmap and the cluster bitmap."""
        cs = self.cs
        mft_clusters = MFT_RECORDS * REC // cs
        in_use = [r for r, n in self.nodes.items() if n.flags & 1] + list(range(16))
        in_use += [n.ext for n in self.nodes.values() if getattr(n, "ext", None) and n.flags & 1]
        mft_bits = bytearray(MFT_RECORDS // 8)
        for r in in_use:
            mft_bits[r >> 3] |= 1 << (r & 7)
        nbytes = (self.nclus + 7) // 8
        bm_clusters = (nbytes + cs - 1) // cs
        if not hasattr(self, "bitmap_lcn"):
            self.bitmap_lcn = self._alloc(bm_clusters)
        bits = bytearray(bm_clusters * cs)
        for c in range(self.nclus):
            if self.used[c]:
                bits[c >> 3] |= 1 << (c & 7)
        self._write(self.part + self.bitmap_lcn * cs, bytes(bits))
        names = ["$MFT", "$MFTMirr", "$LogFile", "$Volume", "$AttrDef", None, "$Bitmap", "$Boot",
                 "$BadClus", "$Secure", "$UpCase", "$Extend"]
        for n, name in enumerate(names):
            if name is None:
                continue
            attrs = [attr_res(0x10, si_value()), attr_res(0x30, fn_value(5, 5, name, is_dir=n == 11))]
            if n == 0:
                attrs += [attr_nonres(0x80, [(MFT_LCN, mft_clusters)], MFT_RECORDS * REC, cs=cs),
                          attr_res(0xB0, bytes(mft_bits))]
            elif n == 6:
                attrs.append(attr_nonres(0x80, [(self.bitmap_lcn, bm_clusters)], nbytes, cs=cs))
            self._write(self._rec_off(n), record(n, n if n else 1, 3 if n == 11 else 1, attrs))
        for n in range(12, 16):
            self._write(self._rec_off(n), record(n, 1, 0, []))
        self._write(self.part, self._boot())
        self._write(self.part + self.volume_sectors() * SECTOR, self._boot())   # the backup copy

    def flush(self):
        for node in self.nodes.values():
            for c, data in getattr(node, "stored", []):
                self._write(self.part + c * self.cs, data)
            if node.is_dir and node is not self.root:
                self._write(self.part + node.runs[0][0] * self.cs, b"INDX".ljust(self.cs, b"\x00"))
            for recno, raw in self._records_of(node):
                self._write(self._rec_off(recno), raw)
        self._system()
        self.f.flush()

    # ------------------------------------------------- after the fact

    def delete(self, path):
        """What Windows does: the record is marked free (its sequence number
        goes up), the clusters too; the record keeps everything else."""
        node = self._node(path)
        node.flags &= ~1
        for lcn, n in node.runs:
            for c in range(max(lcn, 0), lcn + n if lcn >= 0 else 0):
                self.used[c] = 0
        raw = bytearray(self.f_read(self._rec_off(node.recno), REC))
        struct.pack_into("<HH", raw, 0x10, node.seq + 1, 0)
        flags = struct.unpack_from("<H", raw, 0x16)[0] & ~1
        struct.pack_into("<H", raw, 0x16, flags)
        node.seq += 1
        self._write(self._rec_off(node.recno), bytes(raw))
        self._system()

    def reuse(self, path, filler=b"\x5a"):
        """A newer file took the space of a deleted one."""
        node = self._node(path)
        for lcn, n in node.runs:
            if lcn >= 0:
                self._write(self.part + lcn * self.cs, filler * (n * self.cs))
                for c in range(lcn, lcn + n):
                    self.used[c] = 1
        self._system()

    def f_read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def close(self):
        self.f.close()


def quick_format(path, size_mb=64):
    """Replay the real mkntfs -Q (64 MB, 4 KB clusters)."""
    recorded.replay(recorded.name_of("ntfs", size_mb, "4K"), path, size_mb)


def offset_bytes(path):
    return os.path.getsize(path)
