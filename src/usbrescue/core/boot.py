"""Boot sector written by the format. Only a first hint: the old volume may
have used another geometry."""

import struct

from .util import u16, u32


def _vbr(disk, off):
    b = disk.read(off, 512)
    if len(b) < 512 or b[510:512] != b"\x55\xaa":
        return None
    if b[3:11] == b"EXFAT   ":
        bps = 1 << b[108]
        cs = bps << b[109]
        return {"fs": "exfat", "cs": cs, "start": off + u32(b, 88) * bps,
                "root": u32(b, 96), "fat_off": off + u32(b, 80) * bps,
                "fat_len": u32(b, 84) * bps, "nclus": u32(b, 92)}
    bps, spc, rsv, nfats = struct.unpack_from("<HBHB", b, 11)
    fatsz = u32(b, 36)
    if bps in (512, 1024, 2048, 4096) and spc and fatsz and u16(b, 22) == 0:
        return {"fs": "fat32", "cs": bps * spc,
                "start": off + (rsv + nfats * fatsz) * bps, "root": u32(b, 44),
                "fat_off": off + rsv * bps, "fat_len": fatsz * bps}
    return None


def read_boot(disk):
    info = _vbr(disk, 0)
    if info:
        return info
    mbr = disk.read(0, 512)
    if len(mbr) == 512 and mbr[510:512] == b"\x55\xaa":
        for i in range(4):
            lba = u32(mbr, 446 + 16 * i + 8)
            if lba:
                info = _vbr(disk, lba * 512)
                if info:
                    return info
    return None
