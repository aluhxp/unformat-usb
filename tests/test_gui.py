"""The window's back end, driven without a display."""

import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QUrl      # noqa: E402

from helpers import files_under                         # noqa: E402
from test_exfat import build, expected_in_folders, in_folders     # noqa: E402
from usbrescue.gui.backend import Backend               # noqa: E402
from usbrescue.gui.tree_model import PENDING, FolderTreeModel     # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def wait_for(app, backend, phase):
    end = time.time() + 30
    while time.time() < end:
        app.processEvents()
        backend._drain()
        if backend.state["phase"] == phase:
            return
        time.sleep(0.01)
    raise AssertionError(f"still {backend.state['phase']!r}, expected {phase!r}")


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
    assert names(scanned) == ["Carpeta sin nombre 6", "Carpeta sin nombre 7", "iconos",
                              "Carpeta sin nombre 9"]
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
    got = {k: v for k, v in files_under(out).items() if k != "_informe_recuperacion.csv"}
    folders = {"/".join(k.split("/")[1:]): v for k, v in got.items()
               if "/" in k and not k.startswith("Archivos sin carpeta/")}
    assert folders == expected_in_folders()
    assert os.path.exists(scanned.state["reportPath"])


def test_unticking_a_folder_leaves_it_out(app, scanned, tmp_path):
    scanned.setChecked(0, False)            # the folder with the 12 trips
    assert scanned.state["selectedFiles"] == 6
    scanned.setWithOrphans(False)
    out = tmp_path / "out"
    scanned.recover(str(out))
    wait_for(app, scanned, "done")
    got = [k for k in files_under(out) if k != "_informe_recuperacion.csv"]
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
    assert path.startswith(scanned._preview_dir)
    assert open(path, "rb").read() == expected_in_folders()["viaje_03/foto_3.jpg"]


def test_unticking_one_file_leaves_only_that_file_out(app, scanned, tmp_path):
    scanned.toggleExpanded(0)
    scanned.selectFolder(names(scanned).index("viaje_03"))
    scanned.setFileChecked(0, False)
    assert scanned.state["selectedFiles"] == 29
    scanned.setWithOrphans(False)
    scanned.recover(str(tmp_path / "out"))
    wait_for(app, scanned, "done")
    got = [k for k in files_under(tmp_path / "out") if k != "_informe_recuperacion.csv"]
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
    got = [k for k in files_under(out) if k != "_informe_recuperacion.csv"]
    assert len(got) == 30 and not any(" (1)" in k for k in got)
    assert backend.state["sumOk"] == 30
    backend.back()
