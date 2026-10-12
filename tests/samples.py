"""Small, valid files of several kinds, built by hand for the tests."""

import struct

from helpers import make_zip


def pdf(title=None, body=b"hola", date="20230512181203"):
    """A minimal PDF with a real cross-reference table."""
    info = b"<< /CreationDate (D:" + date.encode() + b")"
    if title is not None:
        info += b" /Title (" + title.encode("latin-1") + b")"
    info += b" >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [] /Count 0 >>",
               info, b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 3 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def jpeg(taken="2019:07:30 18:04:48", filler=3000):
    """A JPEG shell with an EXIF block saying when it was taken."""
    stamp = taken.encode() + b"\x00"
    # IFD0 with one entry pointing at the EXIF IFD, which holds DateTimeOriginal
    ifd0 = struct.pack("<HHHII", 1, 0x8769, 4, 1, 26) + struct.pack("<I", 0)
    exif = struct.pack("<HHHII", 1, 0x9003, 2, len(stamp), 44) + struct.pack("<I", 0)
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd0 + exif + stamp
    app1 = b"Exif\x00\x00" + tiff
    return (b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
            + b"\xff\xdb\x00\x04\x00\x00" + b"\xff\xda\x00\x02" + bytes(range(1, 200)) * (filler // 199)
            + b"\xff\xd9")


def mp3(artist="Los Panchos", title="Sabor a mí", filler=4000):
    def frame(name, text):
        body = b"\x03" + text.encode("utf-8")
        return name + struct.pack(">I", len(body)) + b"\x00\x00" + body

    frames = frame(b"TPE1", artist) + frame(b"TIT2", title)
    size = len(frames)
    synch = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x03\x00\x00" + synch + frames + b"\xff\xfb\x90\x00" + b"\x55" * filler


def docx(text, title=None):
    members = {
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": ("<w:document><w:body><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:body></w:document>" % text).encode(),
    }
    if title is not None:
        members["docProps/core.xml"] = (
            "<cp:coreProperties><dc:title>%s</dc:title>"
            "<dcterms:modified xsi:type=\"dcterms:W3CDTF\">2022-03-07T10:20:30Z</dcterms:modified>"
            "</cp:coreProperties>" % title).encode()
    return make_zip(members)
