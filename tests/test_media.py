"""Only photos and videos: a quick rescue that still keeps their folders."""

from factory import exfat_image as X
from helpers import blob, files_under, run, standard_tree
from usbrescue.core import model as ev
from usbrescue.core.kinds import is_media


def drive(path, extra):
    X.mkfs(path)
    img = X.ExfatImage(path)
    for name, data in {**standard_tree(), **extra}.items():
        img.add(name, data)
    img.flush()
    return img


def test_only_photos_and_videos_come_out_each_in_its_folder(tmp_path):
    path = tmp_path / "pendrive.img"
    img = drive(path, {"Fotos/Cumpleaños/video.mp4": b"\x00\x00\x00\x1cftypisom" + blob(3, 20000)})
    img.windows_quick_format()
    img.close()
    out = tmp_path / "out"
    run(path, str(out), find_orphans=False)               # the full rescue, to compare
    full = files_under(out)

    media = tmp_path / "media"
    from usbrescue.core.session import Session
    s = Session(str(path))
    list(s.scan())
    finished = [e for e in s.recover(str(media), only_media=True) if isinstance(e, ev.RecoverFinished)][0]
    s.close()
    got = files_under(media)
    wanted = {k: v for k, v in full.items() if is_media(k)}
    assert got.keys() - {k for k in got if k.startswith("_")} == wanted.keys() | \
        {k for k in got if k.startswith(ev.Names().orphan_dir)}
    assert all(got[k] == v for k, v in wanted.items())
    assert len(wanted) == 13 and any(k.endswith("Cumpleaños/video.mp4") for k in got)
    assert finished.ok == 13
    # the folders around them are kept: Fotos/viaje_03/foto_3.jpg, not a flat pile
    assert all(k.count("/") >= 2 for k in wanted)


def test_photos_without_a_folder_come_too_but_nothing_else(tmp_path):
    path = tmp_path / "pendrive.img"
    img = drive(path, {"suelta.jpg": b"\xff\xd8\xff\xe0" + blob(4, 9000) + b"\xff\xd9"})
    img.windows_quick_format()
    img.close()
    from usbrescue.core.session import Session
    s = Session(str(path))
    list(s.scan())
    list(s.recover(str(tmp_path / "out"), only_media=True))
    s.close()
    loose = [k for k in files_under(tmp_path / "out") if k.startswith(ev.Names().orphan_dir)]
    assert loose and all(k.endswith(".jpg") for k in loose)
