#!/usr/bin/env python3
"""Read-only door to a removable drive, for when reading it needs privileges.

It is started with elevated rights, so it is kept tiny and standalone: it
opens ONE device read-only, refuses anything that is not a removable or USB
drive, and answers read requests on its standard input and output. It cannot
write, and it imports nothing from the rest of the program.

Protocol (little endian):
  on start       ->  b"USBR1", int32 status (0 = ok, else errno), uint64 size
  request        <-  uint64 offset, uint32 length        (length 0 = quit)
  reply          ->  int32 status, uint32 length, then that many bytes
"""

import os
import stat
import struct
import sys

MAGIC = b"USBR1"
MAX_READ = 64 * 1024 * 1024
MAC = sys.platform == "darwin"
ALIGN = 4096            # macOS raw disks read only whole, aligned sectors


def is_removable(dev):
    """True for a drive (or a partition of one) that is removable or on USB."""
    node = os.path.realpath(f"/sys/dev/block/{os.major(dev)}:{os.minor(dev)}")
    if os.path.exists(os.path.join(node, "partition")):
        node = os.path.dirname(node)
    try:
        with open(os.path.join(node, "removable")) as f:
            if f.read().strip() == "1":
                return True
    except OSError:
        pass
    return "/usb" in node


def mac_is_external(path):
    """diskutil's word on a /dev/(r)diskN: external or removable, never internal."""
    import plistlib
    import re
    import subprocess
    m = re.fullmatch(r"/dev/r?(disk\d+)(s\d+)?", path)
    if not m:
        return False
    try:
        info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", m.group(1)],
                                             capture_output=True, timeout=20).stdout)
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException):
        return False
    return bool(info.get("RemovableMediaOrExternalDevice")) or info.get("Internal") is False


def mac_size(fd):
    import fcntl
    block = struct.unpack("<I", fcntl.ioctl(fd, 0x40046418, b"\0" * 4))[0]     # DKIOCGETBLOCKSIZE
    count = struct.unpack("<Q", fcntl.ioctl(fd, 0x40086419, b"\0" * 8))[0]     # DKIOCGETBLOCKCOUNT
    return block * count


def open_source(path):
    """Returns (fd, size). Raises OSError or PermissionError."""
    st = os.stat(path)
    if MAC and (stat.S_ISBLK(st.st_mode) or stat.S_ISCHR(st.st_mode)):
        if not mac_is_external(path):
            raise PermissionError("not an external drive")
        fd = os.open(path, os.O_RDONLY)
        return fd, mac_size(fd)
    if stat.S_ISBLK(st.st_mode):
        if not is_removable(st.st_rdev):
            raise PermissionError("not a removable drive")
    elif os.geteuid() == 0 or not stat.S_ISREG(st.st_mode):
        # plain files are served only without privileges (that is how the
        # tests run it); with privileges, nothing but a removable drive
        raise PermissionError("not a removable drive")
    fd = os.open(path, os.O_RDONLY)
    return fd, os.lseek(fd, 0, os.SEEK_END)


def aligned_read(fd, length, offset):
    start = offset - offset % ALIGN
    end = -(-(offset + length) // ALIGN) * ALIGN
    data = os.pread(fd, end - start, start)
    return data[offset - start:offset - start + length]


def serve(fd, inp, out, aligned=False):
    while True:
        head = inp.read(12)
        if len(head) < 12:
            return
        offset, length = struct.unpack("<QI", head)
        if length == 0:
            return
        try:
            n = min(length, MAX_READ)
            data = aligned_read(fd, n, offset) if aligned else os.pread(fd, n, offset)
            out.write(struct.pack("<iI", 0, len(data)) + data)
        except OSError as e:
            out.write(struct.pack("<iI", e.errno or 5, 0))
        out.flush()


def main(path=None):
    out, inp = sys.stdout.buffer, sys.stdin.buffer
    try:
        path = path or sys.argv[1]
        fd, size = open_source(path)
    except (OSError, IndexError) as e:
        out.write(MAGIC + struct.pack("<iQ", getattr(e, "errno", None) or 1, 0))
        out.flush()
        return 1
    out.write(MAGIC + struct.pack("<iQ", 0, size))
    out.flush()
    serve(fd, inp, out, aligned=MAC and path.startswith("/dev/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
