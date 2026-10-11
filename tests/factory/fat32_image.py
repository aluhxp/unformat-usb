"""Builds FAT32 test images: the real mkfs.vfat formats a file, and this
module writes folders and files into it."""

import shutil
import struct
import subprocess

MKFS = shutil.which("mkfs.vfat") or "/usr/sbin/mkfs.vfat"
EOC = 0x0FFFFFFF
DATE = (2021 - 1980) << 9 | 3 << 5 | 14
TIME = 10 << 11 | 30 << 5


def mkfs(path, size_mb=64):
    with open(path, "ab") as f:
        f.truncate(size_mb * 1024 * 1024)
    subprocess.run([MKFS, "-F", "32", "-s", "8", "-S", "512", str(path)],
                   check=True, capture_output=True)


class _Dir:
    def __init__(self):
        self.children = {}
        self.clusters = []


class _File:
    def __init__(self, data):
        self.data = data
        self.clusters = []


class Fat32Image:
    def __init__(self, path):
        self.f = open(path, "r+b")
        b = self.f.read(512)
        self.bps, spc, self.rsv, self.nfats = struct.unpack_from("<HBHB", b, 11)
        self.cs = self.bps * spc
        self.fatsz = struct.unpack_from("<I", b, 36)[0]
        self.root_cluster = struct.unpack_from("<I", b, 44)[0]
        self.data = (self.rsv + self.nfats * self.fatsz) * self.bps
        self.next = self.root_cluster + 1
        self.fat = {}
        self.root = _Dir()
        self.root.clusters = [self.root_cluster]
        self.serial = 0

    def coff(self, c):
        return self.data + (c - 2) * self.cs

    def _alloc(self, n):
        got = list(range(self.next, self.next + n))
        self.next += n
        for x, y in zip(got, got[1:]):
            self.fat[x] = y
        self.fat[got[-1]] = EOC
        return got

    def add(self, path, data):
        *dirs, name = path.split("/")
        node = self.root
        for d in dirs:
            node = node.children.setdefault(d, _Dir())
        node.children[name] = _File(data)

    def _entries(self, name, node):
        self.serial += 1
        alias = f"F{self.serial:07d}DAT".encode()
        s = 0
        for byte in alias:
            s = (((s & 1) << 7) + (s >> 1) + byte) & 0xFF
        units = name.encode("utf-16-le") + b"\x00\x00"
        if len(units) % 26:
            units += b"\xff" * (26 - len(units) % 26)
        parts = [units[i:i + 26] for i in range(0, len(units), 26)]
        out = b""
        for seq in range(len(parts), 0, -1):
            p = parts[seq - 1]
            e = bytearray(32)
            e[0] = seq | (0x40 if seq == len(parts) else 0)
            e[1:11], e[11], e[13] = p[0:10], 0x0F, s
            e[14:26], e[28:32] = p[10:22], p[22:26]
            out += e
        is_dir = isinstance(node, _Dir)
        first = node.clusters[0] if node.clusters else 0
        e = bytearray(32)
        e[0:11], e[11] = alias, 0x10 if is_dir else 0x20
        struct.pack_into("<HH", e, 22, TIME, DATE)
        struct.pack_into("<H", e, 20, first >> 16)
        struct.pack_into("<H", e, 26, first & 0xFFFF)
        struct.pack_into("<I", e, 28, 0 if is_dir else len(node.data))
        return out + e

    def _dot(self, name, cluster):
        e = bytearray(32)
        e[0:11], e[11] = name.ljust(11).encode(), 0x10
        struct.pack_into("<HH", e, 22, TIME, DATE)
        struct.pack_into("<H", e, 20, cluster >> 16)
        struct.pack_into("<H", e, 26, cluster & 0xFFFF)
        return bytes(e)

    def _allocate(self, d):
        for name, node in d.children.items():
            if isinstance(node, _Dir):
                slots = 2 + sum(2 + len(n) // 13 for n in node.children)
                node.clusters = self._alloc(max(1, (slots * 32 + 32 + self.cs - 1) // self.cs))
            elif node.data:
                node.clusters = self._alloc((len(node.data) + self.cs - 1) // self.cs)
        for node in d.children.values():
            if isinstance(node, _Dir):
                self._allocate(node)

    def _write_tree(self, d, parent_cluster=None):
        body = b""
        if parent_cluster is not None:
            body = self._dot(".", d.clusters[0]) + self._dot("..", parent_cluster)
        body += b"".join(self._entries(n, node) for n, node in d.children.items())
        assert len(body) <= len(d.clusters) * self.cs, "folder does not fit"
        self.f.seek(self.coff(d.clusters[0]))
        self.f.write(body.ljust(len(d.clusters) * self.cs, b"\x00"))
        me = 0 if parent_cluster is None else d.clusters[0]
        for node in d.children.values():
            if isinstance(node, _Dir):
                self._write_tree(node, me)
            elif node.clusters:
                self.f.seek(self.coff(node.clusters[0]))
                self.f.write(node.data)

    def flush(self):
        self._allocate(self.root)
        self._write_tree(self.root)
        for k in range(self.nfats):
            base = (self.rsv + k * self.fatsz) * self.bps
            for c, nxt in self.fat.items():
                self.f.seek(base + 4 * c)
                self.f.write(struct.pack("<I", nxt))
        self.f.flush()

    def close(self):
        self.f.close()
