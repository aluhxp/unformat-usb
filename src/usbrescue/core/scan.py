"""One pass over the whole source looking for folder blocks, FAT32 and exFAT
at the same time. It is a generator so callers can act while it runs."""

from .ntfs import header_ok as ntfs_header_ok
from .util import ENTRY, SECTOR, u16, u32

CHUNK = 32 * 1024 * 1024

DOT = b".          \x10"
DOTDOT = b"..         \x10"
ATTR_LFN, ATTR_DIR, ATTR_VOL = 0x0F, 0x10, 0x08
INVALID_SFN = set(b'"*+,./:;<=>?[\\]|')

EX_FILE, EX_STREAM, EX_NAME = 0x85, 0xC0, 0xC1


def plausible_sfn(e):
    first, attr = e[0], e[11]
    if first in (0x00, 0x20) or attr & 0xC0:
        return False
    for i, b in enumerate(e[:11]):
        if b < 0x20 and not (i == 0 and b == 0x05):
            return False
        if b in INVALID_SFN and not (first == 0x2E and b == 0x2E):
            return False
    return True


def exfat_set_ok(buf, i, allow_deleted):
    if i + 96 > len(buf):
        return False
    t0, t1, t2 = buf[i], buf[i + 32], buf[i + 64]
    if allow_deleted:
        t0, t1, t2 = t0 | 0x80, t1 | 0x80, t2 | 0x80
    if (t0, t1, t2) != (EX_FILE, EX_STREAM, EX_NAME):
        return False
    sec, nlen = buf[i + 1], buf[i + 35]
    return nlen > 0 and sec == 1 + (nlen + 14) // 15


def live_set_follows(buf, i):
    """A live File+Stream+Name set at an entry boundary later in this sector."""
    for q in range(i + ENTRY, i + SECTOR - 3 * ENTRY + 1, ENTRY):
        if buf[q] == EX_FILE and exfat_set_ok(buf, q, False):
            return True
    return False


def exfat_root_ok(buf, i):
    """First sector of an exFAT root folder: it opens with the volume's own
    entries (label, allocation bitmap, upcase table)."""
    if i + 128 > len(buf):
        return False
    types = [buf[i + ENTRY * k] for k in range(4)]
    return types[0] in (0x83, 0x03, 0x81) and 0x81 in types and 0x82 in types


def find_exfat_roots(buf, lim):
    """Offsets inside buf of sectors that look like the start of an exFAT root."""
    firsts = buf[0:lim:SECTOR]
    out = []
    for code in (0x83, 0x03, 0x81):
        k = firsts.find(bytes([code]))
        while k != -1:
            if exfat_root_ok(buf, k * SECTOR):
                out.append(k * SECTOR)
            k = firsts.find(bytes([code]), k + 1)
    return sorted(out)


def scan_blocks(disk, want_deleted):
    """Yields, in disk order:
         ("fat_dot", offset, own_cluster, parent_cluster)   a FAT32 folder
         ("fat_ref", offset, cluster)                       a FAT32 entry naming a folder
         ("ex_start", offset)                               a sector starting an exFAT folder
         ("ex_root", offset)                                a sector starting an exFAT root
         ("ntfs_rec", offset, bytes)                        an NTFS file record
         ("progress", bytes_scanned)                        after each chunk
    """
    off = 0
    while off < disk.size:
        buf = disk.read(off, CHUNK + 128)
        if not buf:
            break
        lim = min(CHUNK, len(buf))

        # FAT32: a folder is a sector-aligned '.' entry followed by '..'
        i = buf.find(DOT)
        while i != -1 and i < lim:
            if (off + i) % SECTOR == 0 and buf[i + 32:i + 44] == DOTDOT:
                own = u16(buf, i + 20) << 16 | u16(buf, i + 26)
                par = u16(buf, i + 52) << 16 | u16(buf, i + 58)
                if own >= 2:
                    yield ("fat_dot", off + i, own, par)
            i = buf.find(DOT, i + 1)

        # FAT32: entries with the folder attribute (to find names in what is
        # left of the old root)
        attrs = buf[11:lim:ENTRY]
        j = attrs.find(b"\x10")
        while j != -1:
            p = j * ENTRY
            e = buf[p:p + ENTRY]
            if e[0] not in (0x2E, 0xE5) and plausible_sfn(e):
                cl = u16(e, 20) << 16 | u16(e, 26)
                if cl >= 2:
                    yield ("fat_ref", off + p, cl)
            j = attrs.find(b"\x10", j + 1)

        # exFAT: a sector that starts with a File+Stream+Name entry set. One
        # that starts with a deleted set is a folder too when a live set
        # follows in the same sector: on a drive in use, the first file of a
        # folder is often one that was deleted.
        firsts = buf[0:lim:SECTOR]
        found = []
        for code in (EX_FILE, 0x05):
            k = firsts.find(bytes([code]))
            while k != -1:
                p = k * SECTOR
                if code == EX_FILE:
                    ok = exfat_set_ok(buf, p, want_deleted)
                else:
                    ok = exfat_set_ok(buf, p, True) and (want_deleted or live_set_follows(buf, p))
                if ok:
                    found.append(off + p)
                k = firsts.find(bytes([code]), k + 1)
        for s in sorted(found):
            yield ("ex_start", s)
        for p in find_exfat_roots(buf, lim):
            yield ("ex_root", off + p)

        # NTFS: a sector that starts a file record
        k = firsts.find(b"F")
        while k != -1:
            p = k * SECTOR
            if ntfs_header_ok(buf, p):
                size = u32(buf, p + 0x1C)
                raw = buf[p:p + size] if p + size <= len(buf) else disk.read(off + p, size)
                yield ("ntfs_rec", off + p, raw)
            k = firsts.find(b"F", k + 1)

        off += CHUNK
        yield ("progress", min(off, disk.size))
