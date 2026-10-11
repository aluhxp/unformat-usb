"""Looking at files and rescuing folders before the scan has finished."""

from helpers import files_under, standard_tree
from test_exfat import FRAGMENTED, build
from usbrescue.core import model as ev
from usbrescue.core.session import Session, file_key


def formatted(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    return path


def scan_until_first_folders(session):
    """Runs the scan up to the moment folders start to show, and hands back
    the generator so the caller can let it finish later."""
    scan = session.scan()
    for e in scan:
        if isinstance(e, ev.FolderFound) and e.name == "viaje_03":
            return scan
    raise AssertionError("no folder announced during the scan")


def test_a_folder_can_be_rescued_while_the_scan_is_still_running(tmp_path):
    session = Session(str(formatted(tmp_path)))
    scan = scan_until_first_folders(session)
    assert session.result is None                       # really mid-scan
    trip = next(c for c, name in session.live._names.items() if name == "viaje_03")
    events = list(session.recover(str(tmp_path / "out"), plans=session.live_plans([trip])))
    assert [type(e) for e in events][-1] is ev.RecoverFinished
    got = {p.split("/")[-1]: d for p, d in files_under(tmp_path / "out").items()}
    assert got == {"foto_3.jpg": standard_tree()["Fotos/viaje_03/foto_3.jpg"],
                   "notas.txt": standard_tree()["Fotos/viaje_03/notas.txt"]}
    list(scan)                                          # and the scan still completes
    assert len(session.result.plans) == 30
    session.close()


def test_what_was_rescued_early_is_not_copied_again(tmp_path):
    session = Session(str(formatted(tmp_path)))
    scan = scan_until_first_folders(session)
    trip = next(c for c, name in session.live._names.items() if name == "viaje_03")
    plans = session.live_plans([trip])
    list(session.recover(str(tmp_path / "out"), plans=plans))
    done = {file_key(p[1]) for p in plans}
    list(scan)
    events = list(session.recover(str(tmp_path / "out"), skip=done, with_orphans=False))
    assert sum(isinstance(e, ev.FileRecovered) for e in events) == 28
    assert not any(" (1)" in p for p in files_under(tmp_path / "out"))
    session.close()


def test_a_fragmented_file_can_be_previewed(tmp_path):
    session = Session(str(formatted(tmp_path)))
    list(session.scan())
    videos = next(c for c, ents in session.result.contents.items()
                  if any(en.name == "a.bin" for en in ents))
    a = next(en for en in session.folder_files(videos) if en.name == "a.bin")
    assert session.read_file(a, 10**9) == FRAGMENTED["Videos/a.bin"]
    assert session.read_file(a, 5000) == FRAGMENTED["Videos/a.bin"][:5000]
    session.close()
