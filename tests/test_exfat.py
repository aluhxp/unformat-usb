import os
import shutil

import pytest

from factory import exfat_image as X
from helpers import below_top, blob, files_under, make_zip, md5_of, run, standard_tree
from usbrescue.core import model as ev
from usbrescue.core.session import Session

FRAGMENTED = {"Videos/a.bin": blob(1, 30000), "Videos/b.bin": blob(2, 50000)}
ROOT_NOTE = b"una nota suelta en la raiz\n" * 20
ROOT_ZIP = make_zip({"uno.txt": b"primero" * 300, "dos/tres.txt": b"segundo" * 500})
AUTORUN = b"[autorun]\r\nicon=iconos\\usb.ico"


def build(path, cluster="4K"):
    X.mkfs(path, cluster=cluster)
    img = X.ExfatImage(path)
    for name, data in standard_tree().items():
        img.add(name, data)
    img.add_interleaved("Videos/a.bin", FRAGMENTED["Videos/a.bin"],
                        "Videos/b.bin", FRAGMENTED["Videos/b.bin"])
    img.add("notas.txt", ROOT_NOTE)
    img.add("trabajo.zip", ROOT_ZIP)
    img.add("autorun.inf", AUTORUN)
    img.flush()
    return img


@pytest.fixture
def windows_formatted(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    assert X.fsck(path) in (None, 0), "the test image itself must be a valid exFAT volume"
    img.windows_quick_format()
    img.close()
    return path


def in_folders(dest):
    """Recovered files that had a folder, keyed without their first-level folder."""
    return {below_top(p): data for p, data in files_under(dest).items()
            if "/" in p and not p.startswith("_ROOT_AND_ORPHANS/")}


def expected_in_folders():
    return {below_top(p): data for p, data in {**standard_tree(), **FRAGMENTED}.items()}


def test_every_file_inside_a_folder_comes_back_intact(windows_formatted, tmp_path):
    result, _, _ = run(windows_formatted, tmp_path / "out")
    assert result.fs == "exfat"
    assert in_folders(tmp_path / "out") == expected_in_folders()


def test_names_with_accents_and_emoji_survive(windows_formatted, tmp_path):
    run(windows_formatted, tmp_path / "out")
    assert any("/Año 2020 ñandú 🎉/informe final con un nombre bastante largo.txt" in "/" + p
               for p in files_under(tmp_path / "out"))


def test_fragmented_files_are_rebuilt_from_the_old_fat(windows_formatted, tmp_path):
    result, _, recovered = run(windows_formatted, tmp_path / "out")
    assert (result.fat_state, result.fragmented, result.chained) == ("kept", 2, 2)
    by_name = {os.path.basename(e.path): e for e in recovered if isinstance(e, ev.FileRecovered)}
    for name in ("a.bin", "b.bin"):
        assert by_name[name].method == "fat_chain"
        assert by_name[name].warnings == []


def test_first_level_names_are_lost_but_reported(windows_formatted, tmp_path):
    result, _, _ = run(windows_formatted, tmp_path / "out")
    tops = {p.split("/")[0] for p in files_under(tmp_path / "out")}
    unnamed = {t for t in tops if t.startswith("UNNAMED_FOLDER_")}
    assert len(unnamed) == result.unnamed_tops == 3      # Fotos, Documentos, Videos


def test_autorun_gives_a_folder_its_name_back(windows_formatted, tmp_path):
    result, _, _ = run(windows_formatted, tmp_path / "out")
    assert list(result.renamed.values()) == ["iconos"]
    assert files_under(tmp_path / "out")["iconos/usb.ico"] == standard_tree()["iconos/usb.ico"]


def test_root_files_come_back_as_orphans(windows_formatted, tmp_path):
    _, _, recovered = run(windows_formatted, tmp_path / "out")
    orphans = {p: d for p, d in files_under(tmp_path / "out").items()
               if p.startswith("_ROOT_AND_ORPHANS/")}
    assert ROOT_NOTE in orphans.values()
    assert ROOT_ZIP in orphans.values()
    assert AUTORUN in orphans.values()
    status = {e.path.rsplit(".", 1)[-1]: e.status for e in recovered if isinstance(e, ev.OrphanRecovered)}
    assert status["zip"] == "verified"


def test_folders_are_announced_while_the_scan_is_still_running(windows_formatted):
    _, scanned, _ = run(windows_formatted)
    kinds = [type(e) for e in scanned]
    last_progress = len(kinds) - 1 - kinds[::-1].index(ev.ScanProgress)
    assert kinds.index(ev.GeometryCalibrated) < last_progress
    assert kinds.index(ev.FolderFound) < last_progress
    assert kinds[-1] is ev.ScanFinished


def test_every_announced_folder_ends_up_placed(windows_formatted):
    result, scanned, _ = run(windows_formatted)
    found = {e.cluster for e in scanned if isinstance(e, ev.FolderFound)}
    placed = {e.cluster for e in scanned if isinstance(e, ev.FolderPlaced)}
    placed |= {e.cluster for e in scanned if isinstance(e, ev.FolderFound) and e.parent is not None}
    assert found == set(result.contents) == placed


def test_the_source_is_never_modified(windows_formatted, tmp_path):
    before = md5_of(windows_formatted)
    os.chmod(windows_formatted, 0o444)      # a write attempt would fail loudly
    run(windows_formatted, tmp_path / "out")
    assert md5_of(windows_formatted) == before


def test_real_mkfs_exfat_reformat(tmp_path):
    path = tmp_path / "pendrive.img"
    build(path).close()
    X.mkfs(path)                            # the real formatter, same settings
    result, _, _ = run(path, tmp_path / "out")
    assert in_folders(tmp_path / "out") == expected_in_folders()
    assert result.fat_state == "kept"


def projects_tree():
    """Many folders with files in between, like a drive that was really used."""
    tree = {}
    for i in range(40):
        tree[f"Proyectos/p_{i:02d}/main_{i:02d}.py"] = blob(200 + i, 3000 + 900 * i)
        tree[f"Proyectos/relleno_{i:02d}.bin"] = blob(300 + i, 4096 * (1 + i % 7))
        tree[f"Proyectos/p_{i:02d}/src/lib_{i:02d}.py"] = blob(400 + i, 2000 + 300 * i)
    return tree


def test_reformat_with_a_different_cluster_size(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path, cluster="4K")
    img = X.ExfatImage(path)
    img.add("primero.bin", blob(9, 200_000))    # what the new format will overwrite
    for name, data in projects_tree().items():
        img.add(name, data)
    old_start = img.heap
    img.flush()
    img.close()
    X.mkfs(path, cluster="32K")

    result, _, _ = run(path, tmp_path / "out")
    assert (result.geometry.cs, result.geometry.start) == (4096, old_start)
    assert result.fat_state == "missing"        # the old FAT cannot be located
    # file names are unique here; the first-level folder lost its name
    got = {p.split("/")[-1]: d for p, d in files_under(tmp_path / "out").items()}
    want = {p.split("/")[-1]: d for p, d in projects_tree().items()}
    assert {k: got.get(k) for k in want} == want
    assert any(p.endswith("/p_07/src/lib_07.py") for p in files_under(tmp_path / "out"))


@pytest.mark.xfail(reason="known limit: with a handful of adjacent folders, half of them "
                          "overwritten by the new format, the old geometry is ambiguous")
def test_different_cluster_size_on_a_nearly_empty_drive(tmp_path):
    path = tmp_path / "pendrive.img"
    old_start = build(path, cluster="4K").heap
    X.mkfs(path, cluster="32K")
    result, _, _ = run(path, tmp_path / "out")
    assert (result.geometry.cs, result.geometry.start) == (4096, old_start)


def test_volume_inside_a_partition_table(tmp_path):
    inner = tmp_path / "volume.img"
    img = build(inner)
    img.windows_quick_format()
    img.close()
    disk = tmp_path / "disk.img"
    mbr = bytearray(512)
    mbr[446 + 4] = 0x07
    mbr[446 + 8:446 + 12] = (2048).to_bytes(4, "little")
    mbr[446 + 12:446 + 16] = (os.path.getsize(inner) // 512).to_bytes(4, "little")
    mbr[510:512] = b"\x55\xaa"
    with open(disk, "wb") as out, open(inner, "rb") as src:
        out.write(mbr.ljust(2048 * 512, b"\x00"))
        shutil.copyfileobj(src, out)
    run(disk, tmp_path / "out")
    assert in_folders(tmp_path / "out") == expected_in_folders()


def test_unreadable_sectors_are_zero_filled_and_reported(windows_formatted, tmp_path):
    session = Session(str(windows_formatted))
    list(session.scan())
    plan = next(p for p in session.result.plans if p[1].name == "tesis.bin")
    bad = session.result.geometry.coff(plan[2][0][0])
    original = session.disk._raw

    def flaky(off, n):
        if off < bad + 512 and off + n > bad:
            raise OSError("simulated bad sector")
        return original(off, n)

    session.disk._raw = flaky
    events = list(session.recover(str(tmp_path / "out")))
    session.close()
    tesis = next(e for e in events if isinstance(e, ev.FileRecovered) and e.path.endswith("tesis.bin"))
    assert "bad_sectors" in tesis.warnings
    want = standard_tree()["Documentos/tesis.bin"]
    assert files_under(tmp_path / "out")[tesis.path.replace(os.sep, "/")] == b"\x00" * 512 + want[512:]


def test_nothing_recoverable_is_said_plainly(tmp_path):
    path = tmp_path / "empty.img"
    X.mkfs(path, size_mb=16)
    result, scanned, _ = run(path)
    assert result is None
    assert isinstance(scanned[-1], ev.NothingFound)
