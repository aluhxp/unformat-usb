"""What the windows talk to: it runs the engine on a worker thread and turns
its events into properties and a tree the screens can show."""

import csv
import os
import queue
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..cli.main import METHODS, ORPHAN_STATUS, WARNINGS
from ..core import model as ev
from ..core.diagnose import diagnose
from ..core.session import Session, UnsafeDestination
from ..core.util import fmt_size as _fmt_size
from ..devices import Device, list_removable
from .tree_model import FolderTreeModel

def fmt_size(n):
    return _fmt_size(n).replace(".", ",")     # decimal comma, as in Spanish


NAMES = ev.Names(unnamed_folder="Carpeta sin nombre {}", lost_parent="Carpetas sueltas",
                 orphan_dir="Archivos sin carpeta", orphan_file="archivo_{}")


class Backend(QObject):
    changed = Signal()
    devicesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree = FolderTreeModel(self)
        self._devices = []
        self._events = queue.Queue()
        self._session = None
        self._device = None
        self._s = {}
        self._reset_state()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._drain)
        self._timer.start()

    def _reset_state(self):
        self._s = dict(
            phase="pick",           # pick | diagnosing | diagnosed | scanning | scanned
                                    # | recovering | done | nothing | error
            error="", sourceName="", sourceDetail="",
            verdict="", diagFat=False, diagRoot=False, diagRootFolders=0,
            scanProgress=0.0, scanEta=-1, foundFiles=0, foundFolders=0, foundBytes=0,
            orphanCount=0, rootRecovered=False, withOrphans=True,
            selectedFiles=0, selectedBytes=0,
            recProgress=0.0, recEta=-1, recSpeed=0.0, recCurrent="", recDone=0, recTotal=0,
            sumOk=0, sumWarned=0, sumOrphans=0, sumUnnamed=0, destPath="", reportPath="")

    def _set(self, **values):
        self._s.update(values)
        self.changed.emit()

    # ------------------------------------------------------------ properties

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._s

    @Property(QObject, constant=True)
    def tree(self):
        return self._tree

    @Property("QVariantList", notify=devicesChanged)
    def devices(self):
        return [dict(path=d.path, name=d.name, size=fmt_size(d.size), transport=d.transport,
                     fs=d.fs, readable=d.readable) for d in self._devices]

    @Property(str, constant=True)
    def defaultDestination(self):
        return os.path.join(os.path.expanduser("~"), "Recuperado")

    @Slot(float, result=str)
    def size(self, n):
        return fmt_size(int(n))

    # -------------------------------------------------------------- choosing

    @Slot()
    def refreshDevices(self):
        self._devices = [d for d in self._devices if d.transport == "image"] + list_removable()
        self.devicesChanged.emit()

    @Slot(QUrl)
    def addImage(self, url):
        path = url.toLocalFile()
        if not os.path.isfile(path):
            return
        self._devices = [d for d in self._devices if d.path != path]
        self._devices.insert(0, Device(path, os.path.basename(path), os.path.getsize(path),
                                       "image", "", os.access(path, os.R_OK)))
        self.devicesChanged.emit()

    @Slot(int)
    def choose(self, index):
        if not 0 <= index < len(self._devices):
            return
        d = self._device = self._devices[index]
        if not d.readable:
            self._set(phase="error", error="no_permission", sourceName=d.name)
            return
        self._tree.clear()
        self._reset_state()
        self._set(phase="diagnosing", sourceName=d.name, sourceDetail=fmt_size(d.size))
        self._run(self._do_diagnose)

    @Slot()
    def back(self):
        self._close()
        self._tree.clear()
        self._reset_state()
        self.changed.emit()

    def _close(self):
        if self._session:
            self._session.close()
            self._session = None

    # --------------------------------------------------------------- workers

    def _run(self, work):
        threading.Thread(target=self._guard, args=(work,), daemon=True).start()

    def _guard(self, work):
        try:
            work()
        except UnsafeDestination:
            self._events.put(("error", "same_device"))
        except PermissionError:
            self._events.put(("error", "no_permission"))
        except OSError as e:
            self._events.put(("error", "io:" + str(e)))

    def _do_diagnose(self):
        self._close()
        self._session = Session(self._device.path, names=NAMES)
        self._events.put(("diagnosis", diagnose(self._session.disk)))

    @Slot()
    def scan(self):
        self._set(phase="scanning", scanProgress=0.0, scanEta=-1)
        self._scan_started = time.time()
        self._run(self._do_scan)

    def _do_scan(self):
        for e in self._session.scan():
            self._events.put(("scan", e))

    @Slot(QUrl)
    def recoverTo(self, url):
        self.recover(url.toLocalFile())

    @Slot(str)
    def recover(self, dest):
        folders, files, size = self._tree.selected()
        r = self._session.result
        paths = {r.paths[c] for c in folders} | {""}
        with_orphans = self._s["withOrphans"]
        self._set(phase="recovering", recProgress=0.0, recDone=0, recTotal=files, recEta=-1,
                  destPath=dest, recCurrent="")
        self._rec_started = time.time()
        self._run(lambda: self._do_recover(dest, paths, with_orphans))

    def _do_recover(self, dest, paths, with_orphans):
        os.makedirs(dest, exist_ok=True)
        report = os.path.join(dest, "_informe_recuperacion.csv")
        with open(report, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ruta", "tamano_bytes", "fecha", "estado", "metodo"])
            for e in self._session.recover(dest, folders=paths, with_orphans=with_orphans):
                if isinstance(e, ev.FileRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                "; ".join(WARNINGS[x] for x in e.warnings) or "ok", METHODS[e.method]])
                elif isinstance(e, ev.OrphanRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                ORPHAN_STATUS[e.status], METHODS[e.method]])
                self._events.put(("recover", e))
        self._events.put(("report", report))

    # ---------------------------------------------------- events, UI thread

    def _drain(self):
        tree_dirty = False
        updates = {}
        for _ in range(4000):
            try:
                kind, e = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                updates.update(phase="error", error=e)
            elif kind == "diagnosis":
                updates.update(phase="diagnosed", verdict=e.verdict, diagFat=e.old_fat,
                               diagRoot=e.old_root, diagRootFolders=len(e.root_folders))
            elif kind == "report":
                updates.update(reportPath=e)
            elif kind == "scan":
                tree_dirty |= self._on_scan(e, updates)
            elif kind == "recover":
                self._on_recover(e, updates)
        if tree_dirty:
            self._tree.refresh()
            _, files, size = self._tree.selected()
            updates.update(selectedFiles=files, selectedBytes=size)
        if updates:
            self._set(**updates)

    def _on_scan(self, e, updates):
        s = self._s
        if isinstance(e, ev.ScanProgress):
            frac = e.done / e.total if e.total else 1.0
            elapsed = time.time() - self._scan_started
            eta = int(elapsed / frac - elapsed) if frac > 0.02 else -1
            updates.update(scanProgress=frac, scanEta=eta)
        elif isinstance(e, ev.FolderFound):
            self._tree.folder_found(e.cluster, e.parent, e.name, e.files, e.size)
            updates.update(
                foundFolders=updates.get("foundFolders", s["foundFolders"]) + 1,
                foundFiles=updates.get("foundFiles", s["foundFiles"]) + e.files,
                foundBytes=updates.get("foundBytes", s["foundBytes"]) + e.size)
            return True
        elif isinstance(e, ev.FolderPlaced):
            self._tree.folder_placed(e.cluster, e.parent, e.name, NAMES.unnamed_folder)
            return True
        elif isinstance(e, ev.TreeReset):
            self._tree.clear()
            updates.update(foundFolders=0, foundFiles=0, foundBytes=0)
        elif isinstance(e, ev.NothingFound):
            updates.update(phase="nothing")
        elif isinstance(e, ev.ScanFinished):
            r = e.result
            self._tree.rebuild(r)
            _, files, size = self._tree.selected()
            updates.update(phase="scanned", scanProgress=1.0, scanEta=0,
                           foundFolders=len(r.contents), foundFiles=len(r.plans),
                           foundBytes=r.total_bytes, orphanCount=len(r.orphans),
                           rootRecovered=r.root_recovered, sumUnnamed=r.unnamed_tops,
                           selectedFiles=files, selectedBytes=size)
        return False

    def _on_recover(self, e, updates):
        s = self._s
        if isinstance(e, ev.CopyProgress):
            frac = e.done / e.total if e.total else 1.0
            elapsed = max(time.time() - self._rec_started, 0.001)
            updates.update(recProgress=frac, recSpeed=e.done / elapsed,
                           recEta=int(elapsed / frac - elapsed) if frac > 0.02 else -1)
        elif isinstance(e, ev.FileRecovered):
            updates.update(recDone=updates.get("recDone", s["recDone"]) + 1, recCurrent=e.path)
        elif isinstance(e, ev.OrphanRecovered):
            updates.update(recCurrent=e.path)
        elif isinstance(e, ev.RecoverFinished):
            updates.update(phase="done", recProgress=1.0, sumOk=e.ok, sumWarned=e.warned,
                           sumOrphans=e.orphans_saved)

    # ------------------------------------------------------------ tree, misc

    @Slot(int)
    def toggleExpanded(self, row):
        self._tree.toggle_expanded(row)

    @Slot(int, bool)
    def setChecked(self, row, value):
        self._tree.set_checked(row, value)
        _, files, size = self._tree.selected()
        self._set(selectedFiles=files, selectedBytes=size)

    @Slot(bool)
    def setWithOrphans(self, value):
        self._set(withOrphans=value)

    @Slot()
    def openDestination(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._s["destPath"]))

    @Slot()
    def openReport(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._s["reportPath"]))
