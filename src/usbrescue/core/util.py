import struct

SECTOR = 512
ENTRY = 32
CLUSTER_SIZES = [512 << k for k in range(0, 17)]  # 512 B .. 32 MB


def fmt_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def sanitize(name):
    bad = '<>:"/\\|?*\x00'
    name = "".join("_" if c in bad or ord(c) < 32 else c for c in name)
    name = name.strip().rstrip(".")
    return (name or "_")[:240]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]
