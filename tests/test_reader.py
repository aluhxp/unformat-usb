"""Reading the way Windows and macOS force on a whole drive."""

import os
import random
import threading

from usbrescue.core import rawdisk
from usbrescue.core.reader import Source


def test_aligned_reads_and_no_pread_give_the_same_bytes(tmp_path):
    path = tmp_path / "disk.img"
    data = random.Random(1).randbytes(64 * 4096)
    path.write_bytes(data)
    plain = Source(str(path))
    strict = Source(str(path))
    strict.align = rawdisk.ALIGN                # as on a physical drive
    strict._seek_lock = threading.Lock()        # as on Windows

    reads = []
    real = strict._pread

    def watch(n, off):
        reads.append((off, n))
        return real(n, off)

    strict._pread = watch
    rnd = random.Random(2)
    for _ in range(300):
        off = rnd.randrange(len(data))
        n = rnd.randrange(1, 20000)
        assert strict.read(off, n) == plain.read(off, n) == data[off:off + n]
    assert all(off % 4096 == 0 for off, _ in reads)
    assert all((off + n) % 4096 == 0 or off + n == len(data) for off, n in reads)


def test_drive_names_per_system():
    assert rawdisk.is_windows_drive(r"\\.\PhysicalDrive2")
    assert rawdisk.windows_disk_number(r"\\.\PhysicalDrive12") == 12
    assert not rawdisk.is_windows_drive("/dev/sdb")
    assert not rawdisk.needs_alignment(os.devnull)
