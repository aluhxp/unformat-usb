"""Read-only access to the source (an image file or a raw device)."""

import os

from .util import SECTOR


class Source:
    """Never opened for writing. Unreadable sectors come back as zeros."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb", buffering=0)
        self.f.seek(0, os.SEEK_END)
        self.size = self.f.tell()
        self.bad_sectors = 0

    def close(self):
        self.f.close()

    def _raw(self, off, n):
        self.f.seek(off)
        out = bytearray()
        while len(out) < n:
            c = self.f.read(n - len(out))
            if not c:
                break
            out += c
        return out

    def read(self, off, n):
        if off < 0 or off >= self.size or n <= 0:
            return b""
        n = min(n, self.size - off)
        try:
            return bytes(self._raw(off, n))
        except OSError:
            # sector by sector; unreadable ones are filled with zeros
            out = bytearray()
            pos = off
            while pos < off + n:
                step = min(SECTOR - pos % SECTOR, off + n - pos)
                try:
                    out += self._raw(pos, step)
                except OSError:
                    out += b"\x00" * step
                    self.bad_sectors += 1
                pos += step
            return bytes(out)
