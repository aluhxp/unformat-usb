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
