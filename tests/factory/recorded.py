"""What a real formatter writes, recorded once on Linux and replayed where
it does not exist (Windows, macOS), so every system tests against the same
real mkfs.exfat / mkfs.vfat output.

Recording formats a file full of a marker byte: every sector that no longer
holds the marker was written by the formatter (zeros included), and is kept.
Replaying writes those sectors, which is exactly what the formatter does."""

import os
import struct
import zlib

HERE = os.path.join(os.path.dirname(__file__), "recorded")
MARKS = (0xA5, 0x5A)
CHUNK = 1 << 20

def name_of(kind, size_mb, cluster=""):
    return f"{kind}-{size_mb}M{'-' + cluster if cluster else ''}.bin"


def available(name):
    return os.path.exists(os.path.join(HERE, name))


def _formatted(run_mkfs, size, mark, scratch):
    fill = bytes([mark]) * CHUNK
    with open(scratch, "wb") as f:
        for _ in range(size // CHUNK):
            f.write(fill)
    run_mkfs(scratch)
    return fill


def record(run_mkfs, size_mb, name, scratch):
    """run_mkfs(path) formats the file at path. The file is formatted twice,
    full of two different marker bytes: a byte that is not its marker in
    one of the two was written by the formatter. (A formatter writes some
    things a few bytes at a time, not whole sectors.)"""
    size = size_mb * 1024 * 1024
    one, two = scratch + ".1", scratch + ".2"
    fill1 = _formatted(run_mkfs, size, MARKS[0], one)
    fill2 = _formatted(run_mkfs, size, MARKS[1], two)
    runs = []
    with open(one, "rb") as f1, open(two, "rb") as f2:
        pos = 0
        while True:
            x, y = f1.read(CHUNK), f2.read(CHUNK)
            if not x:
                break
            if x != fill1[:len(x)] or y != fill2[:len(y)]:
                for i in range(len(x)):
                    a, b = x[i], y[i]
                    if a == MARKS[0] and b == MARKS[1]:
                        continue
                    value = a if a != MARKS[0] else b
                    off = pos + i
                    if runs and runs[-1][0] + len(runs[-1][1]) == off:
                        runs[-1][1].append(value)
                    else:
                        runs.append([off, bytearray([value])])
            pos += len(x)
    out = zlib.compressobj(9)
    with open(os.path.join(HERE, name), "wb") as dst:
        for off, data in runs:
            dst.write(out.compress(struct.pack("<QI", off, len(data)) + bytes(data)))
        dst.write(out.flush())
    os.remove(one)
    os.remove(two)


def replay(name, path, size_mb):
    with open(path, "ab") as f:
        f.truncate(size_mb * 1024 * 1024)
    with open(os.path.join(HERE, name), "rb") as src:
        raw = zlib.decompress(src.read())
    with open(path, "r+b") as f:
        p = 0
        while p < len(raw):
            off, n = struct.unpack_from("<QI", raw, p)
            p += 12
            f.seek(off)
            f.write(raw[p:p + n])
            p += n
