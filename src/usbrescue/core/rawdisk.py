"""What a whole drive needs that an image file does not, per system.

Windows (\\\\.\\PhysicalDrive1) and macOS (/dev/rdisk4) only read whole
sectors at sector-aligned offsets, and do not say their size through
seek; Linux block devices do both like a file."""

import os
import struct
import sys

ALIGN = 4096        # a multiple of every sector size in use (512 and 4096)

IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
DKIOCGETBLOCKSIZE = 0x40046418
DKIOCGETBLOCKCOUNT = 0x40086419


def is_windows_drive(path):
    p = path.replace("/", "\\").lower()
    return p.startswith("\\\\.\\physicaldrive") or p.startswith("\\\\?\\physicaldrive")


def is_mac_disk(path):
    return sys.platform == "darwin" and os.path.basename(path).startswith(("disk", "rdisk")) \
        and path.startswith("/dev/")


def needs_alignment(path):
    return is_windows_drive(path) or is_mac_disk(path)


def windows_disk_number(path):
    tail = path.replace("/", "\\").lower().rsplit("physicaldrive", 1)[-1]
    return int(tail) if tail.isdigit() else None


def size_of(fd, path):
    """Size in bytes of an open file or drive."""
    if is_windows_drive(path):
        return _windows_length(fd)
    if is_mac_disk(path):
        import fcntl
        block = struct.unpack("<I", fcntl.ioctl(fd, DKIOCGETBLOCKSIZE, b"\0" * 4))[0]
        count = struct.unpack("<Q", fcntl.ioctl(fd, DKIOCGETBLOCKCOUNT, b"\0" * 8))[0]
        return block * count
    return os.lseek(fd, 0, os.SEEK_END)


def _windows_length(fd):
    import ctypes
    import msvcrt
    from ctypes import wintypes
    handle = msvcrt.get_osfhandle(fd)
    out = ctypes.c_longlong(0)
    got = wintypes.DWORD(0)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ok = k32.DeviceIoControl(
        wintypes.HANDLE(handle), IOCTL_DISK_GET_LENGTH_INFO, None, 0,
        ctypes.byref(out), ctypes.sizeof(out), ctypes.byref(got), None)
    if not ok:
        raise OSError(ctypes.get_last_error() or 5, "cannot tell the size of the drive")
    return out.value


def windows_disks_of_folder(folder):
    """Numbers of the physical disks a folder's volume lies on (usually one).
    Empty when Windows cannot say (a network share, say)."""
    import ctypes
    from ctypes import wintypes
    drive = os.path.splitdrive(os.path.abspath(folder))[0]
    if len(drive) != 2 or drive[1] != ":":
        return set()
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    handle = k32.CreateFileW(f"\\\\.\\{drive}", 0, 3, None, 3, 0, None)   # no access: just ask
    if handle in (None, wintypes.HANDLE(-1).value):
        return set()
    try:
        buf = ctypes.create_string_buffer(8 + 24 * 16)
        got = wintypes.DWORD(0)
        if not k32.DeviceIoControl(handle, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, None, 0,
                                   buf, len(buf), ctypes.byref(got), None):
            return set()
        count = struct.unpack_from("<I", buf.raw, 0)[0]
        # each extent: disk number (4 bytes, padded to 8), start and length (8 each)
        return {struct.unpack_from("<I", buf.raw, 8 + 24 * i)[0] for i in range(min(count, 16))}
    finally:
        k32.CloseHandle(handle)


def is_admin():
    if sys.platform == "win32":
        import ctypes
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except OSError:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0
