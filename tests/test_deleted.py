"""A drive that was not formatted: bring back only what was deleted."""

import csv
import os

from factory import exfat_image as X
from helpers import files_under, run
from usbrescue.core.model import FileRecovered

PHOTO = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 40       # ~10 KB
NOTE = b"lista de la compra: pan, leche\n" * 300
KEPT = b"this one was never deleted\n" * 200


def drive_with_deletions(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    img.add("Fotos/Cumpleaños 2023/tarta.jpg", PHOTO)
    img.add("Fotos/Cumpleaños 2023/se queda.txt", KEPT)
    img.add("Documentos/compras.txt", NOTE)
    img.add("Documentos/otro que se queda.txt", KEPT)
    img.flush()
    img.delete("Fotos/Cumpleaños 2023/tarta.jpg")
    img.delete("Documentos/compras.txt")
    img.reuse("Documentos/compras.txt")      # a newer file took its space
    img.close()
    return path


def test_only_the_deleted_files_come_back_in_their_folders(tmp_path):
    out = tmp_path / "out"
    result, _, recovered = run(drive_with_deletions(tmp_path), out, include_deleted="only")
    names = sorted(en.name for _, en, _, _ in result.plans)
    assert names == ["compras.txt", "tarta.jpg"]          # whole names, nothing live
    got = files_under(out)
    assert got["Fotos/Cumpleaños 2023/tarta.jpg"] == PHOTO
    warnings = {os.path.basename(e.path): e.warnings for e in recovered if isinstance(e, FileRecovered)}
    assert warnings["tarta.jpg"] == []              # all of them were deleted: no need to say it
    assert warnings["compras.txt"] == ["overwritten"]


def test_live_files_are_listed_too_when_asked(tmp_path):
    result, _, _ = run(drive_with_deletions(tmp_path), include_deleted=True)
    names = {en.name for _, en, _, _ in result.plans}
    assert {"tarta.jpg", "compras.txt", "se queda.txt", "otro que se queda.txt"} <= names


def test_without_asking_deleted_files_stay_out(tmp_path):
    result, _, _ = run(drive_with_deletions(tmp_path))
    names = {en.name for _, en, _, _ in result.plans}
    assert "tarta.jpg" not in names and "se queda.txt" in names


def test_live_files_never_come_back_as_loose_ones(tmp_path):
    out = tmp_path / "out"
    run(drive_with_deletions(tmp_path), out, include_deleted="only")
    for name, data in files_under(out).items():
        assert KEPT[:40] not in data, name
