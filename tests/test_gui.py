"""The window's back end, driven without a display."""

import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl, qInstallMessageHandler   # noqa: E402
from PySide6.QtGui import QGuiApplication               # noqa: E402

from helpers import files_under                         # noqa: E402
from test_exfat import build, expected_in_folders, in_folders     # noqa: E402
from usbrescue.gui.backend import Backend as _Backend   # noqa: E402

# Every backend made here stays alive until the end. Otherwise Python may
# collect one from a worker thread, and Qt (on macOS at least) cannot take a
# window object being destroyed outside the main thread. The program itself
# has a single backend for its whole life.
_ALIVE = []


def Backend(*args, **kwargs):
    backend = _Backend(*args, **kwargs)
    _ALIVE.append(backend)
    return backend
from usbrescue.gui.tree_model import PENDING, FolderTreeModel     # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def wait_for(app, backend, phase):
    end = time.time() + 30
    while time.time() < end:
        app.processEvents()
        backend._drain()
        if backend.state["phase"] == phase:
            return
        time.sleep(0.01)
    raise AssertionError(f"still {backend.state['phase']!r} ({backend.state['error']!r}), expected {phase!r}")


@pytest.fixture
def scanned(app, tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    backend = Backend()
    backend.addImage(QUrl.fromLocalFile(str(path)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    assert backend.state["verdict"] == "structure"
    backend.scan()
    wait_for(app, backend, "scanned")
    yield backend
    backend.back()


def names(backend):
    return [n.name for n in backend.tree.rows]


def test_scan_fills_the_tree_and_the_counters(scanned):
    s = scanned.state
    assert (s["foundFolders"], s["foundFiles"], s["orphanCount"]) == (17, 30, 3)
    assert names(scanned) == ["Unnamed folder 6", "Unnamed folder 7", "iconos",
                              "Unnamed folder 9"]
    assert [n.lost_name for n in scanned.tree.rows] == [True, True, False, True]


def test_a_folder_shows_everything_inside_it(scanned):
    fotos = scanned.tree.rows[0]
    assert fotos.files == 0 and fotos.total_files == 24


def test_expanding_shows_the_subfolders(scanned):
    scanned.toggleExpanded(0)
    assert names(scanned)[1:4] == ["viaje_00", "viaje_01", "viaje_02"]
    scanned.toggleExpanded(0)
    assert len(scanned.tree.rows) == 4


def test_recovering_everything_writes_the_files_and_the_report(app, scanned, tmp_path):
    out = tmp_path / "out"
    scanned.recover(str(out))
    wait_for(app, scanned, "done")
    assert scanned.state["sumOk"] == 30
    got = {k: v for k, v in files_under(out).items() if k != "_recovery_report.csv"}
    folders = {"/".join(k.split("/")[1:]): v for k, v in got.items()
               if "/" in k and not k.startswith("Files without a folder/")}
    assert folders == expected_in_folders()
    assert os.path.exists(scanned.state["reportPath"])


def test_unticking_a_folder_leaves_it_out(app, scanned, tmp_path):
    scanned.setChecked(0, False)            # the folder with the 12 trips
    assert scanned.state["selectedFiles"] == 6
    scanned.setWithOrphans(False)
    out = tmp_path / "out"
    scanned.recover(str(out))
    wait_for(app, scanned, "done")
    got = [k for k in files_under(out) if k != "_recovery_report.csv"]
    assert len(got) == 6 and not any("viaje_" in k for k in got)


def test_a_folder_found_before_its_parent_waits_and_then_moves(app):
    model = FolderTreeModel()
    model.folder_found(20, None, None, 3, 300)          # child first: parent unknown
    model.refresh()
    assert [n.id for n in model.rows] == [PENDING, 20]
    model.folder_found(10, None, None, 1, 100)
    model.folder_placed(20, 10, "viaje", "Carpeta {}")  # the parent names it
    model.folder_placed(10, 0, None, "Carpeta {}")      # and turns out to be top level
    model.nodes[10].expanded = True
    model.refresh()
    assert [(n.id, n.name) for n in model.rows] == [(10, "Carpeta 10"), (20, "viaje")]
    assert model.nodes[10].total_files == 4


def test_a_folder_lists_its_files_and_previews_text(app, scanned):
    scanned.toggleExpanded(0)
    row = names(scanned).index("viaje_03")
    scanned.selectFolder(row)
    assert [f["name"] for f in scanned.state["files"]] == ["foto_3.jpg", "notas.txt"]
    scanned.selectFile(1)
    assert scanned.state["preview"]["kind"] == "text"
    assert scanned.state["preview"]["text"].startswith("viaje numero 3")


def test_a_picture_preview_is_copied_to_this_computer_not_the_drive(app, scanned):
    scanned.toggleExpanded(0)
    scanned.selectFolder(names(scanned).index("viaje_03"))
    scanned.selectFile(0)
    end = time.time() + 10
    while not scanned.state["preview"].get("source") and time.time() < end:
        app.processEvents()
        scanned._drain()
        time.sleep(0.01)
    path = QUrl(scanned.state["preview"]["source"]).toLocalFile()
    assert os.path.normcase(os.path.normpath(path)).startswith(
        os.path.normcase(os.path.normpath(scanned._preview_dir)))
    assert open(path, "rb").read() == expected_in_folders()["viaje_03/foto_3.jpg"]


def test_unticking_one_file_leaves_only_that_file_out(app, scanned, tmp_path):
    scanned.toggleExpanded(0)
    scanned.selectFolder(names(scanned).index("viaje_03"))
    scanned.setFileChecked(0, False)
    assert scanned.state["selectedFiles"] == 29
    scanned.setWithOrphans(False)
    scanned.recover(str(tmp_path / "out"))
    wait_for(app, scanned, "done")
    got = [k for k in files_under(tmp_path / "out") if k != "_recovery_report.csv"]
    assert len(got) == 29 and not any(k.endswith("viaje_03/foto_3.jpg") for k in got)


def test_rescuing_during_the_scan_then_finishing_copies_nothing_twice(app, tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    with open(path, "ab") as f:
        f.truncate(400 * 1024 * 1024)       # more to scan after the folders show up
    backend = Backend()
    backend.addImage(QUrl.fromLocalFile(str(path)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    read = backend._session.disk.read

    def slow(off, n):                        # a slow drive, so the scan is still going
        if n > 1024 * 1024:
            time.sleep(0.05)
        return read(off, n)

    backend._session.disk.read = slow
    backend.scan()
    end = time.time() + 20
    while not backend.state["canRescueNow"] and time.time() < end:
        app.processEvents()
        backend._drain()
        time.sleep(0.005)
    assert backend.state["phase"] == "scanning" and backend.state["canRescueNow"]
    out = tmp_path / "out"
    backend.recover(str(out))
    wait_for(app, backend, "scanning")       # back to the scan after the early rescue
    early = backend.state["rescuedEarly"]
    assert early > 0
    wait_for(app, backend, "scanned")
    backend.setWithOrphans(False)
    backend.recover(str(out))
    wait_for(app, backend, "done")
    got = [k for k in files_under(out) if k != "_recovery_report.csv"]
    assert len(got) == 30 and not any(" (1)" in k for k in got)
    assert backend.state["sumOk"] == 30
    backend.back()


def test_names_are_proposed_applied_and_undone(app, scanned, tmp_path):
    out = tmp_path / "out"
    scanned.setWithOrphans(False)
    scanned.recover(str(out))
    wait_for(app, scanned, "done")
    unnamed = scanned.state["sumUnnamed"]
    scanned.suggestNames()
    wait_for(app, scanned, "naming")
    end = time.time() + 30
    while scanned.state["namesBusy"] and time.time() < end:
        scanned._drain()
        time.sleep(0.01)
    rows = scanned.state["names"]
    assert [(r["current"], r["name"]) for r in rows] == [
        ("Unnamed folder 6", "Photos 2021"),         # photos, each with a short note
        ("Unnamed folder 7", "Documents 2021"),
        ("Unnamed folder 9", "Various 2021")]        # .bin files say nothing
    assert len(rows) == unnamed
    before = sorted(os.listdir(out))

    scanned.applyNames(["Mismo", "mismo", "otro"])  # two folders cannot share a name
    assert scanned.state["namesError"] == "twice" and sorted(os.listdir(out)) == before
    scanned.setNameChecked(1, False)
    scanned.setNameChecked(2, False)
    scanned.applyNames(["Mi carpeta", "ignorada", "ignorada"])
    assert scanned.state["phase"] == "done" and scanned.state["renamed"] == 1
    assert "Mi carpeta" in os.listdir(out) and "Unnamed folder 7" in os.listdir(out)
    assert "Mi carpeta" + os.sep in (out / "_recovery_report.csv").read_text()
    scanned.undoNames()
    assert sorted(os.listdir(out)) == before and scanned.state["sumUnnamed"] == unnamed


def test_in_spanish_folders_and_the_report_are_named_in_spanish(app, tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    backend = Backend()
    assert backend.language == "en"                     # English unless chosen
    backend.setLanguage("es")
    backend.addImage(QUrl.fromLocalFile(str(path)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    backend.scan()
    wait_for(app, backend, "scanned")
    assert "Carpeta sin nombre 6" in names(backend)
    backend.setWithOrphans(False)
    backend.recover(str(tmp_path / "out"))
    wait_for(app, backend, "done")
    report = (tmp_path / "out" / "_informe_recuperacion.csv").read_text(encoding="utf-8")
    assert report.startswith("ruta,") and "Carpeta sin nombre 6" in report
    assert backend.size(1536) == "1,5 KB"
    backend.back()


def test_in_portuguese_folders_are_named_in_portuguese(app, tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    backend = Backend(language="pt")
    assert backend.languageName == "Português"
    assert [x["code"] for x in backend.languages] == ["en", "es", "pt"]
    backend.addImage(QUrl.fromLocalFile(str(path)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    backend.scan()
    wait_for(app, backend, "scanned")
    assert "Pasta sem nome 6" in names(backend)
    backend.back()


def formatted_image(tmp_path):
    path = tmp_path / "pendrive.img"
    img = build(path)
    img.windows_quick_format()
    img.close()
    return path


def test_safe_mode_copies_the_drive_first_and_rescues_from_the_copy(app, tmp_path):
    source = formatted_image(tmp_path)
    backend = Backend()
    backend._default_dest = str(tmp_path / "Recuperado")
    backend.addImage(QUrl.fromLocalFile(str(source)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    assert backend.state["mode"] == "direct"            # a file cannot fail like a drive
    backend.setMode("safe")
    backend.start()
    wait_for(app, backend, "scanned")
    copy = backend.state["imagePath"]
    assert backend.state["imageMade"] and open(copy, "rb").read() == open(source, "rb").read()
    assert backend._session.source_path == copy         # the drive is no longer being read
    backend.setWithOrphans(False)
    backend.recover(str(tmp_path / "out"))
    wait_for(app, backend, "done")
    assert backend.state["sumOk"] == 30
    backend.deleteCopy()
    assert not os.path.exists(copy) and not os.path.exists(copy + ".map")
    backend.back()


def test_pausing_the_copy_goes_back_and_resuming_finishes_it(app, tmp_path):
    source = formatted_image(tmp_path)
    backend = Backend()
    backend._default_dest = str(tmp_path / "Recuperado")
    backend.addImage(QUrl.fromLocalFile(str(source)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    backend.setMode("safe")
    raw = backend._session.disk._raw

    def slow(off, n):
        time.sleep(0.02)
        return raw(off, n)

    backend._session.disk._raw = slow
    backend.start()
    while backend.state["imgProgress"] <= 0:
        app.processEvents()
        backend._drain()
        time.sleep(0.005)
    backend.pauseImaging()
    wait_for(app, backend, "diagnosed")
    assert 0 < backend.state["imgProgress"] < 1 and not backend.state["imageMade"]
    backend._session.disk._raw = raw
    backend.start()
    wait_for(app, backend, "scanned")
    assert open(backend.state["imagePath"], "rb").read() == open(source, "rb").read()
    backend.back()


def test_safe_mode_is_refused_without_room_for_the_copy(app, tmp_path):
    backend = Backend()
    backend.addImage(QUrl.fromLocalFile(str(formatted_image(tmp_path))))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    backend._s["safeFits"] = False
    backend.setMode("safe")
    assert backend.state["mode"] == "direct"
    backend.back()


def test_every_screen_loads_without_a_qml_error(app):
    """A typo in a screen only shows when that screen is opened: open them all."""
    from usbrescue.gui.app import build as build_window

    problems = []
    qInstallMessageHandler(lambda kind, context, text: problems.append(text))
    try:
        engine, backend = build_window(app)
        window = engine.rootObjects()[0]
        for lang, phase in [(lang, phase) for lang in ("en", "es", "pt") for phase in ("pick", "diagnosing", "diagnosed", "imaging", "scanning", "scanned",
                      "recovering", "done", "naming", "nothing", "error")]:
            if backend.language != lang:
                backend.setLanguage(lang)
            for device in (False, True):
                backend._set(phase=phase, isDevice=device, verdict="structure", error="no_permission",
                             sumUnnamed=2, renamed=int(device), namesError="twice" if device else "",
                             names=[dict(current="Unnamed folder 5", name="Fotos 2023",
                                         source="content", example="", files=12, checked=True),
                                    dict(current="Unnamed folder 9", name="Trabajo",
                                         source="original", example="E:/Trabajo/a.xlsx",
                                         files=3, checked=False)])
                app.processEvents()
                loader = window.findChild(object, "pages")
                assert loader.property("item") is not None, f"{phase} did not load"
        backend._set(phase="diagnosed", verdict="in_use")
        app.processEvents()
        window.close()
        engine.deleteLater()
        app.processEvents()
    finally:
        qInstallMessageHandler(None)
    # only what concerns the screens: Qt also chats about fonts on some systems
    assert [p for p in problems if ".qml" in p or "QML" in p] == []


def test_only_photos_and_videos_from_the_window(app, scanned, tmp_path):
    scanned.setMediaOnly(True)
    assert scanned.state["selectedFiles"] == 12            # the photos in Fotos/viaje_*
    out = tmp_path / "out"
    scanned.setWithOrphans(False)
    scanned.recover(str(out))
    wait_for(app, scanned, "done")
    got = [k for k in files_under(out) if not k.startswith("_")]
    assert len(got) == 12 and all(k.endswith(".jpg") and k.count("/") == 2 for k in got)


def test_a_drive_in_use_brings_back_just_what_was_deleted(app, tmp_path):
    from test_deleted import drive_with_deletions
    backend = Backend()
    backend.addImage(QUrl.fromLocalFile(str(drive_with_deletions(tmp_path))))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    assert backend.state["verdict"] == "in_use"
    backend.findDeleted()
    wait_for(app, backend, "scanned")
    s = backend.state
    assert s["deletedOnly"] and s["foundFiles"] == 2 and s["foundFolders"] == 2
    assert names(backend) == ["Fotos", "Documentos"]       # folders with nothing deleted stay out
    out = tmp_path / "out"
    backend.recover(str(out))
    wait_for(app, backend, "done")
    report = (out / "_recovery_report.csv").read_text(encoding="utf-8")
    assert "a newer file used its space" in report
    assert backend.state["sumWarned"] == 1          # the written-over one is worth checking
    backend.back()
    assert not backend.state["deletedOnly"]


def test_nothing_deleted_is_said_plainly(app, tmp_path):
    from factory import exfat_image as X
    path = tmp_path / "pendrive.img"
    X.mkfs(path)
    img = X.ExfatImage(path)
    img.add("Docs/a.txt", b"still here\n" * 100)
    img.flush()
    img.close()
    backend = Backend()
    backend.addImage(QUrl.fromLocalFile(str(path)))
    backend.choose(0)
    wait_for(app, backend, "diagnosed")
    backend.findDeleted()
    wait_for(app, backend, "nothing")
    backend.back()
