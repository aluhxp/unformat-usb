"""Read-only access to the source (an image file or a raw device)."""

import os
import struct
import subprocess
import sys
import threading

from . import rawdisk
from .util import SECTOR

O_BINARY = getattr(os, "O_BINARY", 0)      # Windows would otherwise translate line ends


class Source:
    """Never opened for writing. Unreadable sectors come back as zeros.
    Safe to read from several threads at once."""

    def __init__(self, path):
        self.path = path
        self.bad_sectors = 0
        self._open(path)

    def _open(self, path):
        self.fd = os.open(path, os.O_RDONLY | O_BINARY)
        self.size = rawdisk.size_of(self.fd, path)
        # a whole drive on Windows or macOS reads only whole, aligned sectors
        self.align = rawdisk.ALIGN if rawdisk.needs_alignment(path) else 1
        self._seek_lock = None if hasattr(os, "pread") else threading.Lock()

    def close(self):
        os.close(self.fd)

    def _pread(self, n, off):
        if self._seek_lock is None:
            return os.pread(self.fd, n, off)
        with self._seek_lock:               # Windows has no pread: seek and read together
            os.lseek(self.fd, off, os.SEEK_SET)
            return os.read(self.fd, n)

    def _raw(self, off, n):
        if self.align > 1:
            start = off - off % self.align
            end = min(-(-(off + n) // self.align) * self.align, self.size)
            data = self._read_all(start, end - start)
            return data[off - start:off - start + n]
        return self._read_all(off, n)

    def _read_all(self, off, n):
        out = bytearray()
        while len(out) < n:
            c = self._pread(n - len(out), off + len(out))
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


class HelperSource(Source):
    """A drive this process may not open itself, read through the small
    privileged helper (see helper.py). The system asks the person for
    permission when it starts."""

    def __init__(self, path, command=None):
        self._command = command
        self._lock = threading.Lock()
        super().__init__(path)

    def _open(self, path):
        helper = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "helper.py")
        command = self._command or ["pkexec", sys.executable, helper]
        self.proc = subprocess.Popen(command + [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        head = self.proc.stdout.read(17)
        if len(head) < 17 or head[:5] != b"USBR1":
            self.close()
            raise PermissionError(path)     # refused, cancelled, or no way to ask
        status, self.size = struct.unpack("<iQ", head[5:])
        if status:
            self.close()
            raise PermissionError(path)

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait(timeout=5)

    def _raw(self, off, n):
        out = bytearray()
        with self._lock:
            while len(out) < n:
                self.proc.stdin.write(struct.pack("<QI", off + len(out), n - len(out)))
                self.proc.stdin.flush()
                head = self.proc.stdout.read(8)
                if len(head) < 8:
                    raise OSError(5, "the helper stopped answering")
                status, length = struct.unpack("<iI", head)
                if status:
                    raise OSError(status, os.strerror(status))
                if not length:
                    break
                out += self.proc.stdout.read(length)
        return out
