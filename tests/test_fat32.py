from factory import fat32_image as F
from helpers import below_top, files_under, run, standard_tree
from usbrescue.core import model as ev


def test_fat32_reformat_recovers_what_was_inside_folders(tmp_path):
    path = tmp_path / "pendrive.img"
    F.mkfs(path)
    img = F.Fat32Image(path)
    for name, data in standard_tree().items():
        img.add(name, data)
    img.flush()
    img.close()
    F.mkfs(path)                    # the real formatter wipes both FATs and the root

    result, scanned, _ = run(path, tmp_path / "out")
    assert result.fs == "fat32"
    got = {below_top(p): d for p, d in files_under(tmp_path / "out").items()}
    assert got == {below_top(p): d for p, d in standard_tree().items()}
    assert any(isinstance(e, ev.FolderFound) for e in scanned)
