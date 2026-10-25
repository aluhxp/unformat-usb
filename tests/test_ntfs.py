"""NTFS: a drive that was NTFS before the format comes back from its MFT."""

import datetime
import os
import shutil
import struct
import subprocess

import pytest

from factory import exfat_image as X
from factory import ntfs_image as N
from helpers import blob, files_under, run
from usbrescue.core import ntfs
from usbrescue.core.diagnose import diagnose
from usbrescue.core.model import FileRecovered, NothingFound
from usbrescue.core.reader import Source

PHOTO = b"\xff\xd8\xff\xe0" + blob(1, 50_000)
PDF = b"%PDF-1.4\n" + blob(2, 30_000)
SONG = b"ID3\x03" + blob(3, 120_000)
NOTE = "nota de viaje: llevar bloqueador\n".encode()
TEXT = ("Capítulo uno. Había una vez un pendrive formateado por error. " * 1800).encode()
HOLE = blob(4, 4096) + b"\x00" * 8192 + blob(5, 9000)
ROOT_FILE = blob(6, 2048)


def build(path, **kw):
    img = N.NtfsImage(path, **kw)
    img.add("Fotos/Viaje 2022/playa.jpg", PHOTO, fragments=3)
    img.add("Fotos/Viaje 2022/nota.txt", NOTE)
    img.add("Documentos/informe.pdf", PDF)
    img.add("Documentos/Vacía")
    img.add("Música/Ñandú – canción.mp3", SONG, fragments=4, extension=True)
    img.add("Datos/disperso.bin", HOLE, sparse=True)
    img.add("Datos/libro.txt", TEXT, compressed=True)
    img.add("raíz.bin", ROOT_FILE)
    img.flush()
    return img


EXPECTED = {
    "Fotos/Viaje 2022/playa.jpg": PHOTO,
    "Fotos/Viaje 2022/nota.txt": NOTE,
    "Documentos/informe.pdf": PDF,
    "Música/Ñandú – canción.mp3": SONG,
    "Datos/disperso.bin": HOLE,
    "Datos/libro.txt": TEXT,
}


def test_lznt1_reads_what_it_should():
    for data in (TEXT[:20000], b"abc" * 3000, blob(7, 5000), b"x" * 4096 + b"y" * 10):
        packed = N.lznt1_compress(data)
        assert ntfs.lznt1(packed, len(data)) == data
    assert len(N.lznt1_compress(TEXT[:16384])) < 8192       # it did compress


def test_quick_formatted_ntfs_comes_back_whole(tmp_path):
    path = tmp_path / "pendrive.img"
    build(path).close()
    N.quick_format(path)                    # what the real mkntfs -Q writes
    out = tmp_path / "out"
    result, scanned, recovered = run(path, out)
    assert result.fs == "ntfs"
    assert (result.geometry.cs, result.geometry.start) == (4096, 2 * 4096)
    got = files_under(out)
    for rel, data in EXPECTED.items():
        assert got[rel] == data, rel
    assert got["raíz.bin"] == ROOT_FILE
    assert os.path.join("Documentos", "Vacía") in result.paths.values()   # empty folders too
    assert not any(name.startswith("$") for name in got)    # not the file system's own files
    warnings = {e.path: e.warnings for e in recovered if isinstance(e, FileRecovered)}
    assert all(w == [] for w in warnings.values()), warnings
    methods = {e.path: e.method for e in recovered if isinstance(e, FileRecovered)}
    assert methods[os.path.join("Fotos", "Viaje 2022", "nota.txt")] == "ntfs_resident"
    when = datetime.datetime.fromtimestamp(os.path.getmtime(out / "Documentos" / "informe.pdf"))
    assert when == N.WHEN
    assert result.root_recovered


def test_ntfs_formatted_as_exfat(tmp_path):
    path = tmp_path / "pendrive.img"
    build(path).close()
    X.mkfs(path)                            # the real mkfs.exfat, replayed
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    assert result.fs == "ntfs"
    got = files_under(out)
    for rel, data in EXPECTED.items():
        assert got[rel] == data, rel


def test_a_live_ntfs_gives_back_just_what_was_deleted(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.delete("Fotos/Viaje 2022/playa.jpg")
    img.delete("Documentos/informe.pdf")
    img.reuse("Documentos/informe.pdf")     # a newer file took its space
    img.delete("Música/Ñandú – canción.mp3")
    img.delete("Música")                    # its folder, deleted with it
    img.close()

    d = Source(str(path))
    diag = diagnose(d)
    d.close()
    assert diag.verdict == "in_use"
    assert sorted(diag.current_folders) == ["Datos", "Documentos", "Fotos"]

    out = tmp_path / "out"
    result, _, recovered = run(path, out, include_deleted="only")
    assert result.fs == "ntfs"
    assert sorted(en.name for _, en, _, _ in result.plans) == \
        ["informe.pdf", "playa.jpg", "Ñandú – canción.mp3"]
    got = files_under(out)
    assert got["Fotos/Viaje 2022/playa.jpg"] == PHOTO
    assert got["Música/Ñandú – canción.mp3"] == SONG
    warnings = {os.path.basename(e.path): e.warnings for e in recovered if isinstance(e, FileRecovered)}
    assert warnings["playa.jpg"] == []
    assert warnings["informe.pdf"] == ["overwritten"]

    # the drive as it is now has nothing missing
    result, scanned, _ = run(path)
    assert result is None or not result.plans
    assert result is not None or any(isinstance(e, NothingFound) for e in scanned)


def test_a_folder_whose_record_is_gone(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    viaje = img._node("Fotos/Viaje 2022").recno
    img._write(img._rec_off(viaje), b"\x00" * N.REC)      # its record was written over
    img.close()
    N.quick_format(path)
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    got = files_under(out)
    lost = f"UNNAMED_FOLDER_{viaje}"
    assert got[f"{lost}/playa.jpg"] == PHOTO
    assert got[f"{lost}/nota.txt"] == NOTE
    assert got["Documentos/informe.pdf"] == PDF


def test_ntfs_in_a_partition(tmp_path):
    path = tmp_path / "pendrive.img"
    start = 1024 * 1024
    img = build(path, offset=start)
    mbr = bytearray(512)
    struct.pack_into("<B3sB3sII", mbr, 446, 0, b"\x00\x02\x00", 0x07, b"\xfe\xff\xff",
                     start // 512, (img.size - start) // 512)
    mbr[510:512] = b"\x55\xaa"
    img._write(0, bytes(mbr))
    img._write(start, b"\x00" * 512)        # the volume's boot sector is gone
    img._write(img.size - 512, b"\x00" * 512)    # and its backup
    img.close()
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    assert result.fs == "ntfs"
    assert result.geometry.start == start + 2 * 4096
    got = files_under(out)
    for rel, data in EXPECTED.items():
        assert got[rel] == data, rel


MKNTFS, NTFSCP = shutil.which("mkntfs") or "/usr/sbin/mkntfs", shutil.which("ntfscp") or "/usr/sbin/ntfscp"


@pytest.mark.skipif(not (os.path.exists(MKNTFS) and os.path.exists(NTFSCP)),
                    reason="needs ntfs-3g's mkntfs and ntfscp")
def test_real_ntfs_3g_volume(tmp_path):
    """Files written by ntfs-3g itself, then a real quick format."""
    path = tmp_path / "real.img"
    with open(path, "wb") as f:
        f.truncate(64 * 1024 * 1024)
    subprocess.run([MKNTFS, "-Q", "-F", "-c", "4096", str(path)], check=True, capture_output=True)
    files = {"grande.bin": blob(8, 300_000), "chico.txt": b"hola\n", "foto.jpg": PHOTO}
    for name, data in files.items():
        src = tmp_path / name
        src.write_bytes(data)
        subprocess.run([NTFSCP, str(path), str(src), name], check=True, capture_output=True)
    subprocess.run([MKNTFS, "-Q", "-F", "-c", "4096", str(path)], check=True, capture_output=True)
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    assert result.fs == "ntfs"
    assert files_under(out) == files


def disk_image_with_many_files(tmp_path):
    """An NTFS volume (4 MB) with lots of files, to keep as a .vhd file."""
    inner = tmp_path / "inner.img"
    img = N.NtfsImage(inner, size_mb=4)
    for i in range(10):
        for j in range(4):
            img.add(f"Proyecto {i}/archivo {j}.txt", f"dentro de la imagen {i} {j}\n".encode())
    img.flush()
    img.close()
    return inner.read_bytes()


def test_a_disk_image_kept_on_the_drive_stays_one_file(tmp_path):
    vhd = disk_image_with_many_files(tmp_path)
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.add("Copias/disco.vhd", vhd)
    img.flush()
    img.close()
    N.quick_format(path)
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    got = files_under(out)
    assert got["Copias/disco.vhd"] == vhd
    assert not any("Proyecto" in rel for rel in got)        # what is inside it stays inside it
    for rel, data in EXPECTED.items():
        assert got[rel] == data, rel


def test_an_exfat_drive_holding_an_ntfs_image_is_read_as_exfat(tmp_path):
    vhd = disk_image_with_many_files(tmp_path)
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    img.add("Copias/disco.vhd", vhd)
    img.add("Fotos/playa.jpg", PHOTO)
    img.flush()
    img.windows_quick_format()
    img.close()
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    assert result.fs == "exfat"
    got = files_under(out)
    assert vhd in got.values() and PHOTO in got.values()


def test_the_backup_boot_sector_tells_the_geometry(tmp_path):
    """Formatted as exFAT, with nothing whose content can be checked: the
    copy of the boot sector at the end of the volume still has it."""
    path = tmp_path / "pendrive.img"
    img = N.NtfsImage(path, cs=8192)
    img.add("Datos/a.bin", blob(10, 70_000))
    img.add("Datos/b.dat", blob(11, 90_000))
    img.flush()
    img.close()
    X.mkfs(path)
    out = tmp_path / "out"
    result, _, _ = run(path, out)
    assert result.fs == "ntfs"
    assert result.geometry.cs == 8192
    got = files_under(out)
    assert got["Datos/a.bin"] == blob(10, 70_000) and got["Datos/b.dat"] == blob(11, 90_000)
