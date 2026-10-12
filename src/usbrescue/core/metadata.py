"""A name and a date for a file that lost both, read from inside the file.

Files rescued without a folder come back as "orphan_1234.pdf". What they hold
often says what they are: a document's title, the day a photo was taken, a
song's artist, the first line of a note."""

import datetime
import re
import struct
import zipfile

LABEL_MAX = 60
READ_MAX = 8 * 1024 * 1024


def _tidy(text):
    """One line, trimmed, or None when it says nothing useful."""
    text = re.sub(r"\s+", " ", text or "").strip(" .-_\t")
    if len(text) > LABEL_MAX:
        text = text[:LABEL_MAX].rsplit(" ", 1)[0] if " " in text[:LABEL_MAX] else text[:LABEL_MAX]
    letters = sum(c.isalnum() for c in text)
    if letters < 3 or letters * 2 < len(text):
        return None
    if " " not in text and len(text) > 30:
        return None             # one long unbroken run: encoded data, not words
    return text


# ------------------------------------------------------------------ Office

_XML_TEXT = {
    "docx": ("word/document.xml", r"<w:t(?: [^>]*)?>([^<]*)</w:t>"),
    "pptx": ("ppt/slides/slide1.xml", r"<a:t>([^<]*)</a:t>"),
    "xlsx": ("xl/sharedStrings.xml", r"<t(?: [^>]*)?>([^<]*)</t>"),
    "odt": ("content.xml", r"<text:(?:h|p)[^>]*>([^<]+)<"),
}


def _unescape(text):
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(a, b)
    return text


def office_text(path, ext):
    """The words a document opens with."""
    member, pattern = _XML_TEXT.get(ext, (None, None))
    if not member:
        return None
    try:
        with zipfile.ZipFile(path) as z, z.open(member) as f:
            xml = f.read(READ_MAX).decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    words = ""
    for piece in re.findall(pattern, xml):
        words += _unescape(piece) + " "
        if len(words) > LABEL_MAX * 2:
            break
    return _tidy(words)


# --------------------------------------------------------------------- PDF

def _pdf_string(raw):
    if raw.startswith(b"<"):
        try:
            data = bytes.fromhex(re.sub(rb"\s", b"", raw[1:-1]).decode("ascii"))
        except ValueError:
            return ""
    else:
        body = raw[1:-1]
        body = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), body)
        for a, b in ((rb"\n", b"\n"), (rb"\r", b"\r"), (rb"\t", b"\t"), (rb"\(", b"("),
                     (rb"\)", b")"), (b"\\\\", b"\\")):
            body = body.replace(a, b)
        data = body
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", "replace")
    return data.decode("latin-1")


_PDF_VALUE = rb"\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)"
_PRODUCED_BY = re.compile(r"^(microsoft (word|excel|powerpoint) - |untitled|sin t[ií]tulo)", re.I)


def clean_title(text):
    """A title as people would say it: programs often store their own name
    and the file name in it ('Microsoft Word - letter.docx')."""
    text = re.sub(r"\.(docx?|xlsx?|pptx?|odt)$", "", (text or "").strip(), flags=re.I)
    return _tidy(_PRODUCED_BY.sub("", text))


def pdf_info(data):
    """(title, date) from a PDF's information block, when it is not packed away."""
    title, when = None, None
    m = re.search(rb"/Title" + _PDF_VALUE, data)
    if m:
        title = clean_title(_pdf_string(m.group(1)))
    m = re.search(rb"/CreationDate\s*\(D:(\d{14})", data)
    if m:
        try:
            when = datetime.datetime.strptime(m.group(1).decode(), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return title, when


# -------------------------------------------------------------------- JPEG

def exif_date(data):
    """When a photo was taken, from its EXIF block."""
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker, size = data[pos + 1], struct.unpack_from(">H", data, pos + 2)[0]
        if marker == 0xE1 and data[pos + 4:pos + 10] == b"Exif\x00\x00":
            return _tiff_date(data[pos + 10:pos + 2 + size])
        if marker == 0xDA:
            break
        pos += 2 + size
    return None


def _tiff_date(t):
    if t[:2] not in (b"II", b"MM"):
        return None
    e = "<" if t[:2] == b"II" else ">"

    def entries(off):
        if off + 2 > len(t):
            return {}
        n = struct.unpack_from(e + "H", t, off)[0]
        out = {}
        for i in range(n):
            p = off + 2 + 12 * i
            if p + 12 > len(t):
                break
            tag, _, count, value = struct.unpack_from(e + "HHII", t, p)
            out[tag] = (count, value)
        return out

    def text(entry):
        count, off = entry
        return t[off:off + count].split(b"\x00")[0].decode("ascii", "replace")

    first = entries(struct.unpack_from(e + "I", t, 4)[0])
    found = None
    if 0x8769 in first:                         # the camera's own block
        inner = entries(first[0x8769][1])
        if 0x9003 in inner:                     # the moment the picture was taken
            found = text(inner[0x9003])
    if not found and 0x0132 in first:
        found = text(first[0x0132])
    try:
        return datetime.datetime.strptime(found or "", "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


# --------------------------------------------------------------------- MP3

def _synchsafe(b):
    return b[0] << 21 | b[1] << 14 | b[2] << 7 | b[3]


def id3_tags(data):
    """(artist, title) from the tag at the start of an MP3."""
    if data[:3] != b"ID3" or len(data) < 10:
        return None, None
    version, end = data[3], 10 + _synchsafe(data[6:10])
    pos, found = 10, {}
    while pos + 10 <= min(end, len(data)):
        frame, raw = data[pos:pos + 4], data[pos + 4:pos + 8]
        size = _synchsafe(raw) if version >= 4 else struct.unpack(">I", raw)[0]
        if not frame.strip(b"\x00") or size <= 0:
            break
        body = data[pos + 10:pos + 10 + size]
        if frame in (b"TIT2", b"TPE1") and body:
            codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(body[0], "latin-1")
            found[frame] = body[1:].decode(codec, "replace").split("\x00")[0]
        pos += 10 + size
    return found.get(b"TPE1"), found.get(b"TIT2")


# -------------------------------------------------------------------- text

def first_line(data, link_label):
    """A note's first line, when it reads like words. Rows of a database dump
    and other machine output do not make a name."""
    line = next((ln for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()), "")
    link = re.match(r"\s*https?://(?:www\.)?([^/\s:]+)", line)
    if link:
        return _tidy(link_label.format(link.group(1)))
    digits = sum(c.isdigit() for c in line)
    odd = sum(c in "()[]{};=<>|'\"\\`$%&*+" for c in line)
    if "\t" in line or digits * 4 > len(line) or odd * 12 > len(line):
        return None
    stripped = line.strip()
    if stripped[-1:] in ",;(" or " = " in stripped or stripped.count("_") >= 2:
        return None             # a piece of code or of a query, cut from its file
    return _tidy(line)


# ----------------------------------------------------------------- the lot

TEXT_KINDS = ("txt", "sh", "sql", "ini", "json", "xml", "html")


def describe(path, ext, title="", photo_label="photo {}", link_label="link {}"):
    """(label, date) for a rescued file; either may be None. `title` is one
    already found by the caller; the two labels are how the caller's language
    says "photo taken at ..." and "link to ..."."""
    label, when = clean_title(title), None
    try:
        with open(path, "rb") as f:
            head = f.read(READ_MAX)
    except OSError:
        return label, when
    if ext in _XML_TEXT:
        label = label or office_text(path, ext)
    elif ext == "pdf":
        found, when = pdf_info(head)
        label = label or found
    elif ext == "jpg":
        when = exif_date(head)
        label = label or (photo_label.format(when.strftime("%Y-%m-%d %H.%M.%S")) if when else None)
    elif ext == "mp3":
        artist, song = id3_tags(head)
        label = label or _tidy(" - ".join(x for x in (artist, song) if x))
    elif ext in TEXT_KINDS:
        label = label or first_line(head[:4096], link_label)
    return label, when
