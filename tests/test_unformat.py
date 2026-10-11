"""What the format left behind: the quick diagnosis, and the old root folder."""

from factory import exfat_image as X
from factory import fat32_image as F
from helpers import blob, files_under, run
from test_exfat import build, projects_tree
from usbrescue.core import model as ev
from usbrescue.core.diagnose import diagnose
from usbrescue.core.reader import Source

ROOT_FILE = blob(9, 3000)


def used_drive(path):
    """An exFAT drive with named first-level folders and a file in the root.
    The first file is what a later format with bigger clusters overwrites."""
    X.mkfs(path, cluster="4K")
    img = X.ExfatImage(path)
    img.add("relleno inicial.bin", blob(8, 200_000))
    for name, data in projects_tree().items():
        img.add(name, data)
    img.add("Fotos/playa.jpg", blob(5, 9000))
    img.add("leeme.txt", ROOT_FILE)
    img.flush()
    img.close()


def test_diagnosis_when_only_the_fat_survived(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    d = diagnose(Source(str(path)))
    assert (d.verdict, d.old_fat, d.old_root) == ("structure", True, False)


def test_diagnosis_when_the_old_root_survived(tmp_path):
    path = tmp_path / "pendrive.img"
    used_drive(path)
    X.mkfs(path, cluster="32K")
    d = diagnose(Source(str(path)))
    assert d.verdict == "names_and_structure"
    assert set(d.root_folders) == {"Proyectos", "Fotos"}
    assert d.root_files == 2


def test_diagnosis_of_a_freshly_formatted_empty_drive(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path, size_mb=2048)          # sparse: takes no real space
    d = diagnose(Source(str(path)))
    assert (d.verdict, d.old_fat, d.old_root) == ("looks_empty", False, False)


def test_the_system_folder_windows_adds_is_not_mistaken_for_old_content(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    img.add("System Volume Information/WPSettings.dat", b"x" * 12)
    img.flush()
    img.close()
    assert diagnose(Source(str(path))).old_root is False


def test_new_root_naming_only_system_folders_is_not_announced_as_recovered(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    after = X.ExfatImage(path)          # what Windows writes right after formatting
    after.add("System Volume Information/WPSettings.dat", b"x" * 12)
    after.flush()
    after.close()
    result, scanned, _ = run(path, tmp_path / "out")
    assert result.root_recovered is False
    assert not any(isinstance(e, ev.RootRecovered) for e in scanned)
    assert "System Volume Information/WPSettings.dat" in files_under(tmp_path / "out")


def test_old_root_gives_back_every_first_level_name(tmp_path):
    path = tmp_path / "pendrive.img"
    used_drive(path)
    X.mkfs(path, cluster="32K")
    result, scanned, _ = run(path, tmp_path / "out")
    assert result.root_recovered and result.unnamed_tops == 0
    assert any(isinstance(e, ev.RootRecovered) for e in scanned)
    got = files_under(tmp_path / "out")
    want = {**projects_tree(), "Fotos/playa.jpg": blob(5, 9000), "leeme.txt": ROOT_FILE}
    assert {k: got.get(k) for k in want} == want
    assert not any(p.startswith("UNNAMED_FOLDER_") for p in got)


def test_root_files_are_not_recovered_twice(tmp_path):
    path = tmp_path / "pendrive.img"
    used_drive(path)
    X.mkfs(path, cluster="32K")
    run(path, tmp_path / "out")
    assert list(files_under(tmp_path / "out").values()).count(ROOT_FILE) == 1


def test_exfat_drive_reformatted_as_fat32(tmp_path):
    path = tmp_path / "pendrive.img"
    used_drive(path)
    F.mkfs(path)
    result, _, _ = run(path, tmp_path / "out")
    assert result.fs == "exfat"         # what the drive was, not what it is now
    got = files_under(tmp_path / "out")
    assert {k: got.get(k) for k in projects_tree()} == projects_tree()


def test_folder_entry_split_across_two_clusters_is_not_lost(tmp_path):
    path = tmp_path / "pendrive.img"
    X.mkfs(path, cluster="4K")
    img = X.ExfatImage(path)
    for name, data in projects_tree().items():   # 'Proyectos' needs two clusters
        img.add(name, data)
    img.flush()
    assert len(img.root.children["Proyectos"].clusters) == 2
    img.windows_quick_format()
    img.close()
    result, _, _ = run(path, tmp_path / "out")
    assert result.unnamed_tops == 1              # only 'Proyectos' itself
    got = {"/".join(p.split("/")[1:]): d for p, d in files_under(tmp_path / "out").items()
           if not p.startswith("_ROOT_AND_ORPHANS/")}
    want = {"/".join(p.split("/")[1:]): d for p, d in projects_tree().items()}
    assert got == want
