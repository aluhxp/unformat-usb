"""Orphans: files that were loose in the root, and other data without a folder.

The old root is lost, but its files' data is still there. It is looked for in
the clusters no known file claims, in three ways:
  - whole chains in the old FAT that nothing points to (a fragmented file;
    its clusters are known exactly),
  - clusters that start with the signature of a known file type (a contiguous
    file; where it ends follows from the format itself), and
  - runs of clusters holding text that stop short of filling the last one
    (text files have no signature: notes, scripts, autorun.inf...)."""

import datetime
import mmap
import os
import re
import struct
import zipfile

from .oldfat import to_runs
from .util import sanitize, u32

COPY_BLOCK = 8 * 1024 * 1024
MAX_RUN = 2 * 1024 ** 3   # cap for runs with no known end
SIGNATURES = [
    (b"%PDF-", "pdf"), (b"PK\x03\x04", "zip"), (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc"),
    (b"Rar!\x1a\x07", "rar"), (b"7z\xbc\xaf\x27\x1c", "7z"), (b"GIF8", "gif"),
    (b"\x1a\x45\xdf\xa3", "mkv"), (b"SQLite format 3\x00", "sqlite"),
    (b"\x1f\x8b\x08", "gz"), (b"ID3", "mp3"), (b"MZ", "exe"),
]
TEXT_BYTES = bytes(range(32, 127)) + b"\t\n\r"


def copy_runs(disk, g, runs, nbytes, out, tick=None):
    remaining = nbytes
    for first, count in runs:
        pos, left = g.coff(first), min(remaining, count * g.cs)
        while left > 0:
            data = disk.read(pos, min(left, COPY_BLOCK))
            if not data:
                return
            out.write(data)
            pos += len(data)
            left -= len(data)
            remaining -= len(data)
            if tick:
                tick(len(data))
        if remaining <= 0:
            return


def sniff(head):
    for sig, ext in SIGNATURES:
        if head.startswith(sig):
            if ext == "exe":   # "MZ" is too short: require the PE header
                pe = u32(head, 60) if len(head) >= 64 else len(head)
                if head[pe:pe + 4] != b"PE\x00\x00":
                    continue
            return ext
    if head[4:8] == b"ftyp":
        return "mp4"
    return None


def looks_text(data):
    """Nearly all printable ASCII (accents in UTF-8 or Latin-1 are fine)."""
    data = data.rstrip(b"\x00")
    if not data or b"\x00" in data:
        return False
    rest = data.translate(None, TEXT_BYTES)
    plain = len(data) - len(rest)
    odd = sum(1 for b in rest if b < 128)
    return plain * 100 >= len(data) * 80 and odd * 100 < len(data)


def text_part(data):
    """The text a cluster starts with, up to the first null byte (a text file
    has none: what follows is padding or older leftovers). Returns b"" when
    the cluster does not start with believable text."""
    part = data.split(b"\x00", 1)[0]
    if not looks_text(part):
        return b""
    if len(part) < len(data) and any(data[len(part):]) and len(part) < 32 and part[-1:] != b"\n":
        return b""   # a few letters at the start of a binary
    return part


def text_ext(head):
    """Likely extension of a text file from how it begins."""
    low = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if low.startswith(b"[autorun]"):
        return "autorun.inf"
    if low.startswith(b"[.shellclassinfo]"):
        return "desktop.ini"
    if low.startswith(b"[trash info]"):
        return "trashinfo"
    if low.startswith(b"#!"):
        return "sh"
    if low.startswith((b"<!doctype html", b"<html")):
        return "html"
    if low.startswith(b"<"):
        return "xml"
    if low.startswith((b"{", b"[{")):
        return "json"
    if any(k in low[:4096] for k in (b"create table", b"insert into", b"-- postgresql", b"-- mysql")):
        return "sql"
    if low.startswith(b"["):
        return "ini"
    return "txt"


class Orphan:
    def __init__(self, cluster, ext, runs, exact, status=None, size=None):
        self.cluster, self.ext, self.runs, self.exact = cluster, ext, runs, exact
        self.status = status   # set when found, if there is nothing to verify
        self.size = size       # exact size in bytes, when known
        self.nclus = sum(n for _, n in runs)

    @property
    def method(self):
        return "orphan_chain" if self.exact else "signature"


def find_orphans(disk, g, claimed):
    n = len(claimed)
    kinds = {}
    for c in range(2, n):
        if not claimed[c]:
            k = sniff(disk.read(g.coff(c), 1024))
            if k:
                kinds[c] = k
    used = bytearray(claimed)
    found = []
    fat = g.fat
    if fat:
        lim = min(n, fat.n)
        pointed = bytearray(n)
        for c in range(2, lim):
            if 2 <= fat.t[c] < n:
                pointed[fat.t[c]] = 1
        for c in range(2, lim):
            if claimed[c] or pointed[c] or not fat.t[c]:
                continue
            ch = fat.free_chain(c, claimed)
            if ch and not any(used[x] for x in ch):
                if c not in kinds:
                    first = disk.read(g.coff(c), g.cs)
                    if not first.rstrip(b"\x00") or (len(ch) > 1 and (
                            first[-1] == 0 or 0 < len(text_part(first)) < len(first))):
                        # the file ends inside its first cluster: the rest of
                        # the chain belongs to an older one. If it is text,
                        # the text search below picks it up.
                        continue
                for x in ch:
                    used[x] = 1
                found.append(Orphan(c, kinds.get(c, "bin"), to_runs(ch), True))
    for c in sorted(kinds):
        if used[c]:
            continue
        e = c + 1
        while e < n and not used[e] and e not in kinds and (e - c) * g.cs < MAX_RUN:
            e += 1
        used[c:e] = b"\x01" * (e - c)
        found.append(Orphan(c, kinds[c], [(c, e - c)], False))
    # text: consecutive free clusters of text, up to the one that ends before
    # filling its cluster. It may step on the tail of a run found by
    # signature, because such a run is usually longer than its file.
    taken = bytearray(claimed)
    for o in found:
        if o.exact:
            for first, count in o.runs:
                taken[first:first + count] = b"\x01" * count
        else:
            taken[o.cluster] = 1
    c = 2
    while c < n:
        first, size, closed, head = c, 0, False, b""
        while c < n and not taken[c] and size < MAX_RUN and not closed:
            data = disk.read(g.coff(c), g.cs)
            part = text_part(data)
            if not part:
                break
            head = head or part[:8192]
            size += len(part)
            closed = len(part) < len(data)
            c += 1
        if c == first:
            c += 1
            continue
        if size < 16 and not head.strip():
            continue   # only line breaks
        found.append(Orphan(first, text_ext(head), [(first, c - first)], False,
                            "text" if closed else "text_cut", size))
    found.sort(key=lambda o: o.cluster)
    return found


def zip_end(m, exact):
    """Where the zip that starts at byte 0 ends, or None."""
    pos = m.rfind(b"PK\x05\x06") if exact else m.find(b"PK\x05\x06")
    while pos != -1:
        if pos + 22 <= len(m):
            cd_size, cd_off, clen = struct.unpack_from("<IIH", m, pos + 12)
            if cd_off + cd_size == pos and pos + 22 + clen <= len(m):
                return pos + 22 + clen
        pos = m.rfind(b"PK\x05\x06", 0, pos) if exact else m.find(b"PK\x05\x06", pos + 1)
    return None


def pdf_end(m):
    """Last %%EOF whose startxref points at a table or an object."""
    pos = m.rfind(b"%%EOF")
    while pos != -1:
        tail = m[max(0, pos - 64):pos]
        mt = re.search(rb"startxref\s+(\d+)\s*$", tail)
        if mt:
            x = int(mt.group(1))
            if x < pos and (m[x:x + 4] == b"xref" or re.match(rb"\d+ \d+ obj", m[x:x + 24])):
                end = pos + 5
                while end < len(m) and m[end] in (10, 13):
                    end += 1
                return end
        pos = m.rfind(b"%%EOF", 0, pos)
    return None


def zip_identify(path):
    """(extension, title, date, intact) of a zip or Office file."""
    ext, title, when = "zip", "", None
    with zipfile.ZipFile(path) as z:
        ok = z.testzip() is None
        names = set(z.namelist())
        for marker, e in (("word/document.xml", "docx"), ("xl/workbook.xml", "xlsx"),
                          ("ppt/presentation.xml", "pptx"), ("AndroidManifest.xml", "apk"),
                          ("META-INF/MANIFEST.MF", "jar")):
            if marker in names:
                ext = e
                break
        else:
            if "mimetype" in names:
                mime = z.read("mimetype")
                ext = {b"application/vnd.oasis.opendocument.text": "odt",
                       b"application/vnd.oasis.opendocument.spreadsheet": "ods",
                       b"application/vnd.oasis.opendocument.presentation": "odp",
                       b"application/epub+zip": "epub"}.get(mime.strip(), "zip")
        if ok and "docProps/core.xml" in names:
            core = z.read("docProps/core.xml").decode("utf-8", "replace")
            mt = re.search(r"<dc:title>([^<]*)</dc:title>", core)
            title = mt.group(1).strip() if mt else ""
            mt = re.search(r"<dcterms:modified[^>]*>([^<]*)<", core)
            try:
                when = datetime.datetime.strptime(mt.group(1)[:19], "%Y-%m-%dT%H:%M:%S") if mt else None
            except ValueError:
                when = None
    return ext, title, when, ok


def save_orphan(disk, g, o, folder, file_pattern):
    """Writes the orphan and returns (path, size, date, status), or None when
    it turned out not to be a usable file."""
    stem = file_pattern.format(o.cluster)
    tmp = os.path.join(folder, stem + ".part")
    with open(tmp, "wb") as out:
        copy_runs(disk, g, o.runs, o.nclus * g.cs, out)
    size = os.path.getsize(tmp)
    ext, title, when, end, status = o.ext, "", None, None, None
    if o.size is not None:
        end = min(o.size, size)
    elif size:
        with open(tmp, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
            if ext == "zip":
                end = zip_end(m, o.exact)
            elif ext == "pdf":
                end = pdf_end(m)
                status = "pdf_valid" if end else None
            elif ext == "png":
                p = m.find(b"IEND")
                end = p + 8 if p != -1 else None
                status = "png_complete" if end else None
            if end is None:
                # no recognisable end: drop the zero padding at the tail
                lo = size - g.cs if o.exact else 0
                end = size
                while end > lo and m[end - 1] == 0:
                    end -= 1
    else:
        end = 0
    os.truncate(tmp, end)
    if ext == "zip":
        try:
            ext, title, when, ok = zip_identify(tmp)
            status = "verified" if ok else "damaged"
        except (zipfile.BadZipFile, OSError, ValueError, KeyError, NotImplementedError):
            status = "damaged"
    if not o.exact and (status is None or status == "damaged") and ext in ("zip", "pdf", "png"):
        os.remove(tmp)   # a stray signature with no valid file behind it
        return None
    if status is None:
        status = o.status or ("chain_unverified" if o.exact else "size_approx")
    name = stem
    if title:
        name += " - " + sanitize(title)[:80]
    dest = os.path.join(folder, f"{name}.{ext}")
    os.replace(tmp, dest)
    if when:
        try:
            os.utime(dest, (when.timestamp(), when.timestamp()))
        except (OverflowError, OSError, ValueError):
            pass
    return dest, end, when, status
