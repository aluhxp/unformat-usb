"""Builds exFAT test images without mounting anything: the real mkfs.exfat
formats a file, and this module writes folders and files into it."""

import os
import shutil
import struct
import subprocess

from . import recorded

MKFS = shutil.which("mkfs.exfat") or ("/usr/sbin/mkfs.exfat" if os.path.exists("/usr/sbin/mkfs.exfat") else None)
FSCK = shutil.which("fsck.exfat") or ("/usr/sbin/fsck.exfat" if os.path.exists("/usr/sbin/fsck.exfat") else None)
EOC = 0xFFFFFFFF
TIMESTAMP = (2021 - 1980) << 25 | 3 << 21 | 14 << 16 | 10 << 11 | 30 << 5


def real_mkfs(path, cluster="4K"):
    subprocess.run([MKFS, "-c", cluster, str(path)], check=True, capture_output=True)


def mkfs(path, size_mb=64, cluster="4K"):
    """Replays what the real mkfs.exfat wrote (see recorded.py), so every
    system tests against the same formatter version. USBRESCUE_REAL_MKFS=1
    runs the installed one instead."""
    if MKFS and os.environ.get("USBRESCUE_REAL_MKFS"):
        with open(path, "ab") as f:
            f.truncate(size_mb * 1024 * 1024)
        real_mkfs(path, cluster)
    else:
        recorded.replay(recorded.name_of("exfat", size_mb, cluster), path, size_mb)


def fsck(path):
    """None when this system cannot check (then the check is skipped)."""
    if not FSCK:
        return None
    return subprocess.run([FSCK, "-n", str(path)], capture_output=True, text=True).returncode


class _Dir:
    def __init__(self):
        self.children = {}      # name -> _Dir | _File, in creation order
        self.clusters = []
        self.entry_at = None    # (offset, length) of its entry set, once written


class _File:
    def __init__(self, data):
        self.data = data
        self.clusters = []
        self.partner = None     # file whose clusters alternate with this one's
        self.entry_at = None


class ExfatImage:
    """Describe the tree with add()/add_interleaved(), then flush() once."""

    def __init__(self, path, offset=0):
        self.path, self.offset = path, offset
        self.f = open(path, "r+b")
        b = self._read(0, 512)
        assert b[3:11] == b"EXFAT   "
        self.bps = 1 << b[108]
        self.cs = self.bps << b[109]
        self.fat_off = struct.unpack_from("<I", b, 80)[0] * self.bps
        self.heap = struct.unpack_from("<I", b, 88)[0] * self.bps
        self.nclus = struct.unpack_from("<I", b, 92)[0]
        self.root_cluster = struct.unpack_from("<I", b, 96)[0]
        root = self._read(self.coff(self.root_cluster), self.cs)
        self.system_entries = b""
        for p in range(0, self.cs, 32):
            e = root[p:p + 32]
            if e[0] == 0:
                break
            self.system_entries += e
            if e[0] == 0x81:
                self.bitmap_cluster = struct.unpack_from("<I", e, 20)[0]
                self.bitmap_len = struct.unpack_from("<Q", e, 24)[0]
            elif e[0] == 0x82:
                up_cluster = struct.unpack_from("<I", e, 20)[0]
                up_len = struct.unpack_from("<Q", e, 24)[0]
        self.upcase = self._load_upcase(self._read(self.coff(up_cluster), up_len))
        self.bitmap = bytearray(self._read(self.coff(self.bitmap_cluster), self.bitmap_len))
        self.system_bitmap = bytes(self.bitmap)
        self.fat = {}
        self.root = _Dir()
        self.root.clusters = [self.root_cluster]

    # ------------------------------------------------------------ low level

    def _read(self, off, n):
        self.f.seek(self.offset + off)
        return self.f.read(n)

    def _write(self, off, data):
        self.f.seek(self.offset + off)
        self.f.write(data)

    def coff(self, c):
        return self.heap + (c - 2) * self.cs

    @staticmethod
    def _load_upcase(raw):
        vals = struct.unpack(f"<{len(raw) // 2}H", raw[:len(raw) // 2 * 2])
        table, i, ch = {}, 0, 0
        while i < len(vals) and ch < 0x10000:
            if vals[i] == 0xFFFF and i + 1 < len(vals):
                ch += vals[i + 1]
                i += 2
            else:
                table[ch] = vals[i]
                ch += 1
                i += 1
        return table

    def _alloc(self, n):
        """n consecutive free clusters."""
        run = 0
        for c in range(2, self.nclus + 2):
            bit = c - 2
            if self.bitmap[bit >> 3] >> (bit & 7) & 1:
                run = 0
                continue
            run += 1
            if run == n:
                got = list(range(c - n + 1, c + 1))
                for x in got:
                    self.bitmap[(x - 2) >> 3] |= 1 << ((x - 2) & 7)
                return got
        raise RuntimeError("image full")

    def _nclus(self, nbytes):
        return (nbytes + self.cs - 1) // self.cs

    # -------------------------------------------------------------- content

    def _parent(self, path):
        *dirs, name = path.split("/")
        node = self.root
        for d in dirs:
            node = node.children.setdefault(d, _Dir())
        return node, name

    def add(self, path, data):
        node, name = self._parent(path)
        node.children[name] = _File(data)
        return node.children[name]

    def mkdir(self, path):
        node, name = self._parent(path)
        return node.children.setdefault(name, _Dir())

    def add_interleaved(self, path_a, data_a, path_b, data_b):
        """Two files whose clusters alternate, so both are fragmented."""
        a, b = self.add(path_a, data_a), self.add(path_b, data_b)
        a.partner, b.partner = b, a

    # ---------------------------------------------------------------- flush

    def _entry_set(self, name, node):
        units = name.encode("utf-16-le")
        nlen = len(units) // 2
        up = b"".join(struct.pack("<H", self.upcase.get(u, u))
                      for u in struct.unpack(f"<{nlen}H", units))
        h = 0
        for byte in up:
            h = (((h << 15) | (h >> 1)) + byte) & 0xFFFF
        is_dir = isinstance(node, _Dir)
        size = len(node.clusters) * self.cs if is_dir else len(node.data)
        first = node.clusters[0] if node.clusters else 0
        contiguous = node.clusters == list(range(first, first + len(node.clusters)))
        flags = 0x01 | (0x02 if node.clusters and contiguous else 0)
        if not contiguous:
            for x, y in zip(node.clusters, node.clusters[1:]):
                self.fat[x] = y
            self.fat[node.clusters[-1]] = EOC
        nname = (nlen + 14) // 15
        fe = bytearray(32)
        fe[0], fe[1] = 0x85, 1 + nname
        struct.pack_into("<H", fe, 4, 0x10 if is_dir else 0x20)
        struct.pack_into("<III", fe, 8, TIMESTAMP, TIMESTAMP, TIMESTAMP)
        se = bytearray(32)
        se[0], se[1], se[3] = 0xC0, flags, nlen
        struct.pack_into("<H", se, 4, h)
        struct.pack_into("<Q", se, 8, size)
        struct.pack_into("<I", se, 20, first)
        struct.pack_into("<Q", se, 24, size)
        out = fe + se
        padded = units + b"\x00" * (nname * 30 - len(units))
        for k in range(nname):
            out += b"\xc1\x00" + padded[k * 30:(k + 1) * 30]
        chk = 0
        for i, byte in enumerate(out):
            if i in (2, 3):
                continue
            chk = ((((chk & 1) << 15) | (chk >> 1)) + byte) & 0xFFFF
        struct.pack_into("<H", out, 2, chk)
        return bytes(out)

    @staticmethod
    def _entries_needed(d):
        return sum(2 + (len(n.encode("utf-16-le")) // 2 + 14) // 15 for n in d.children)

    def _allocate(self, d):
        for node in d.children.values():
            if isinstance(node, _Dir):
                node.clusters = self._alloc(max(1, self._nclus(self._entries_needed(node) * 32 + 32)))
            elif not node.clusters and node.data:
                if node.partner is None:
                    node.clusters = self._alloc(self._nclus(len(node.data)))
                else:
                    a, b = node, node.partner
                    na, nb = self._nclus(len(a.data)), self._nclus(len(b.data))
                    block = self._alloc(na + nb)
                    while block:
                        if len(a.clusters) < na:
                            a.clusters.append(block.pop(0))
                        if block and len(b.clusters) < nb:
                            b.clusters.append(block.pop(0))
        for node in d.children.values():
            if isinstance(node, _Dir):
                self._allocate(node)

    def _write_tree(self, d, prefix=b""):
        sets, at = [], len(prefix)
        for n, node in d.children.items():
            es = self._entry_set(n, node)
            node.entry_at = (at, len(es), d)
            sets.append(es)
            at += len(es)
        body = prefix + b"".join(sets)
        assert len(body) <= len(d.clusters) * self.cs, "folder does not fit"
        body += b"\x00" * (len(d.clusters) * self.cs - len(body))
        for i, c in enumerate(d.clusters):
            self._write(self.coff(c), body[i * self.cs:(i + 1) * self.cs])
        for node in d.children.values():
            if isinstance(node, _Dir):
                self._write_tree(node)
            else:
                for i, c in enumerate(node.clusters):
                    self._write(self.coff(c), node.data[i * self.cs:(i + 1) * self.cs]
                                .ljust(self.cs, b"\x00"))

    def flush(self):
        self._allocate(self.root)
        self._write_tree(self.root, self.system_entries)
        self._write(self.coff(self.bitmap_cluster), bytes(self.bitmap))
        for c, nxt in self.fat.items():
            self._write(self.fat_off + 4 * c, struct.pack("<I", nxt))
        self.f.flush()

    def close(self):
        self.f.close()

    # ---------------------------------------------------------- after use

    def _node(self, path):
        node = self.root
        for part in path.split("/"):
            node = node.children[part]
        return node

    def _disk_offset(self, d, at):
        return self.coff(d.clusters[at // self.cs]) + at % self.cs

    def delete(self, path):
        """What deleting a file does: its entries lose their in-use bit and
        its clusters are freed in the bitmap. The data stays where it was."""
        node = self._node(path)
        at, length, d = node.entry_at
        for k in range(0, length, 32):
            off = self._disk_offset(d, at + k)
            t = self._read(off, 1)[0]
            self._write(off, bytes([t & 0x7F]))
        for c in node.clusters:
            self.bitmap[(c - 2) >> 3] &= ~(1 << ((c - 2) & 7)) & 0xFF
        self._write(self.coff(self.bitmap_cluster), bytes(self.bitmap))
        self.f.flush()

    def reuse(self, path, filler=b"N"):
        """A newer file took the space of a deleted one: its clusters are
        written over and marked in use again."""
        node = self._node(path)
        for c in node.clusters:
            self._write(self.coff(c), filler * self.cs)
            self.bitmap[(c - 2) >> 3] |= 1 << ((c - 2) & 7)
        self._write(self.coff(self.bitmap_cluster), bytes(self.bitmap))
        self.f.flush()

    # --------------------------------------------------------------- format

    def windows_quick_format(self):
        """What a Windows quick format was seen to do on a real drive: the
        root cluster is wiped and gets fresh system entries, the bitmap starts
        over, and the FAT keeps its old chains."""
        self._write(self.coff(self.root_cluster),
                    self.system_entries.ljust(self.cs, b"\x00"))
        self._write(self.coff(self.bitmap_cluster), self.system_bitmap)
        self._write(self.fat_off + 4 * self.root_cluster, struct.pack("<I", EOC))
        self.f.flush()
