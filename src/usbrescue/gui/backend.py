"""What the windows talk to: it runs the engine on a worker thread and turns
its events into properties and a tree the screens can show."""

import csv
import os
import queue
import shutil
import tempfile
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..cli.main import METHODS, ORPHAN_STATUS, WARNINGS
from ..core import model as ev
from ..core.diagnose import diagnose
from ..core.orphans import looks_text
from ..core.reader import HelperSource
from ..core.session import Session, UnsafeDestination, file_key
from ..core.util import fmt_size as _fmt_size
from ..devices import Device, list_removable
from .tree_model import FolderTreeModel

def fmt_size(n):
    return _fmt_size(n).replace(".", ",")     # decimal comma, as in Spanish


NAMES = ev.Names(unnamed_folder="Carpeta sin nombre {}", lost_parent="Carpetas sueltas",
                 orphan_dir="Archivos sin carpeta", orphan_file="archivo_{}")


IMAGE_TYPES = ("jpg", "jpeg", "png", "gif", "bmp", "webp")
FILES_SHOWN = 500               # a folder may hold tens of thousands
PREVIEW_IMAGE_LIMIT = 40 * 1024 * 1024
PREVIEW_TEXT_LIMIT = 4000


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
        self._early = None              # folders asked for while the scan runs
        self._excluded = {}             # file key -> (folder, size) of unticked files
        self._done_keys = set()         # files already rescued
        self._folder = None             # folder whose files are listed
        self._preview = None            # entry being previewed
        self._preview_serial = 0
        # pictures to preview are copied here, on this computer, never on the drive
        self._preview_dir = tempfile.mkdtemp(prefix="rescate-vista-")
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
            selectedFiles=0, selectedBytes=0, canRescueNow=False, early=False, rescuedEarly=0,
            needsPermission=False, folderId=-2, folderName="", files=[], filesHidden=0,
            preview={},
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
        self._tree.clear()
        self._forget()
        self._reset_state()
        self._set(phase="diagnosing", sourceName=d.name, sourceDetail=fmt_size(d.size),
                  needsPermission=not d.readable)
        self._run(self._do_diagnose)

    @Slot()
    def back(self):
        self._close()
        self._tree.clear()
        self._forget()
        self._reset_state()
        self.changed.emit()

    def cleanup(self):
        """Call when the program closes."""
        self._close()
        shutil.rmtree(self._preview_dir, ignore_errors=True)

    def _forget(self):
        for name in os.listdir(self._preview_dir):
            os.remove(os.path.join(self._preview_dir, name))
        self._early, self._folder, self._preview = None, None, None
        self._excluded, self._done_keys = {}, set()

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
        d = self._device
        # a drive this process may not open is read through the helper,
        # which makes the system ask for the password
        disk = None if d.readable else HelperSource(d.path)
        self._session = Session(d.path, names=NAMES, disk=disk)
        self._events.put(("diagnosis", diagnose(self._session.disk)))

    @Slot()
    def scan(self):
        self._set(phase="scanning", scanProgress=0.0, scanEta=-1)
        self._scan_started = time.time()
        self._run(self._do_scan)

    def _do_scan(self):
        for e in self._session.scan():
            self._events.put(("scan", e))
            if self._early and self._session.result is None:
                # rescue what was asked for right here, between two steps of
                # the scan: nothing else touches the tree meanwhile
                dest, clusters, skip = self._early
                self._early = None
                paused = time.time()
                plans = self._session.live_plans(clusters)
                self._copy(dest, "early", plans=plans, skip=skip)
                self._events.put(("early_done", (clusters, {file_key(p[1]) for p in plans} - skip)))
                self._scan_started += time.time() - paused
        if self._early:                 # asked at the very last moment
            dest, clusters, skip = self._early
            self._early = None
            r = self._session.result
            self._copy(dest, "recover", folders={r.paths[c] for c in clusters if c in r.paths},
                       skip=skip, with_orphans=False)

    def _copy(self, dest, kind, **options):
        os.makedirs(dest, exist_ok=True)
        report = os.path.join(dest, "_informe_recuperacion.csv")
        new = not os.path.exists(report) or not os.path.getsize(report)
        with open(report, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["ruta", "tamano_bytes", "fecha", "estado", "metodo"])
            for e in self._session.recover(dest, **options):
                if isinstance(e, ev.FileRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                "; ".join(WARNINGS[x] for x in e.warnings) or "ok", METHODS[e.method]])
                elif isinstance(e, ev.OrphanRecovered):
                    w.writerow([e.path, e.size, e.mtime.isoformat() if e.mtime else "",
                                ORPHAN_STATUS[e.status], METHODS[e.method]])
                self._events.put((kind, e))
        self._events.put(("report", report))

    @Slot(QUrl)
    def recoverTo(self, url):
        self.recover(url.toLocalFile())

    @Slot(str)
    def recover(self, dest):
        folders, files, size = self._selection()
        skip = set(self._excluded) | self._done_keys
        self._set(phase="recovering", recProgress=0.0, recDone=0, recTotal=files, recEta=-1,
                  destPath=dest, recCurrent="")
        self._rec_started = time.time()
        if self._session.result is None:
            # the scan is still running: its own thread does the copying
            self._set(early=True)
            self._early = (dest, folders, skip)
            return
        r = self._session.result
        paths = {r.paths[c] for c in folders} | {""}
        with_orphans = self._s["withOrphans"]
        self._run(lambda: self._copy(dest, "recover", folders=paths, skip=skip,
                                     with_orphans=with_orphans))

    def _selection(self):
        """(folders, files, bytes) ticked, minus the files unticked one by one."""
        folders, files, size = self._tree.selected()
        for folder, fsize in self._excluded.values():
            if folder in folders:
                files, size = files - 1, size - fsize
        return folders, files, size

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
            elif kind == "preview":
                serial, target = e
                if serial == self._preview_serial:      # still the file being looked at
                    updates.update(preview=dict(self._s["preview"],
                                                source=QUrl.fromLocalFile(target).toString()))
            elif kind == "scan":
                tree_dirty |= self._on_scan(e, updates)
            elif kind in ("recover", "early"):
                self._on_recover(e, updates, early=kind == "early")
            elif kind == "early_done":
                clusters, keys = e
                self._done_keys |= keys
                self._tree.mark_rescued(clusters)
                tree_dirty = True
                updates.update(phase="scanning", early=False,
                               rescuedEarly=self._s["rescuedEarly"] + len(keys))
        if tree_dirty:
            self._tree.refresh()
            _, files, size = self._selection()
            live = self._session and self._session.live
            updates.update(selectedFiles=files, selectedBytes=size,
                           canRescueNow=bool(live and live.geometry and files))
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
            _, files, size = self._selection()
            if self._s["phase"] == "recovering":
                updates.update(early=False)     # a rescue asked for at the last moment goes on
            else:
                updates.update(phase="scanned")
            updates.update(scanProgress=1.0, scanEta=0,
                           foundFolders=len(r.contents), foundFiles=len(r.plans),
                           foundBytes=r.total_bytes, orphanCount=len(r.orphans),
                           rootRecovered=r.root_recovered, sumUnnamed=r.unnamed_tops,
                           selectedFiles=files, selectedBytes=size)
        return False

    def _on_recover(self, e, updates, early=False):
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
        elif isinstance(e, ev.RecoverFinished) and not early:
            updates.update(phase="done", recProgress=1.0,
                           sumOk=e.ok + self._s["rescuedEarly"], sumWarned=e.warned,
                           sumOrphans=e.orphans_saved)

    # ------------------------------------------------------------ tree, misc

    @Slot(int)
    def toggleExpanded(self, row):
        self._tree.toggle_expanded(row)

    @Slot(int, bool)
    def setChecked(self, row, value):
        self._tree.set_checked(row, value)
        _, files, size = self._selection()
        self._set(selectedFiles=files, selectedBytes=size)

    # ------------------------------------------------- files and previews

    def _entries(self):
        return self._session.folder_files(self._folder) if self._session and self._folder else []

    def _file_rows(self):
        return [dict(name=en.name, size=fmt_size(en.size),
                     date=en.mtime.strftime("%d/%m/%Y") if en.mtime else "",
                     checked=file_key(en) not in self._excluded)
                for en in self._entries()[:FILES_SHOWN]]

    @Slot(int)
    def selectFolder(self, row):
        node = self._tree.node_at(row)
        if node is None or node.id is None or node.id < 0:
            return
        self._folder, self._preview = node.id, None
        self._set(folderId=node.id, folderName=node.name or "", files=self._file_rows(),
                  filesHidden=max(0, len(self._entries()) - FILES_SHOWN), preview={})

    @Slot(int, bool)
    def setFileChecked(self, i, value):
        entries = self._entries()
        if not 0 <= i < len(entries):
            return
        en = entries[i]
        if value:
            self._excluded.pop(file_key(en), None)
        else:
            self._excluded[file_key(en)] = (self._folder, en.size)
        _, files, size = self._selection()
        self._set(files=self._file_rows(), selectedFiles=files, selectedBytes=size)

    @Slot(int)
    def selectFile(self, i):
        entries = self._entries()
        if not 0 <= i < len(entries):
            return
        en = self._preview = entries[i]
        ext = en.name.rsplit(".", 1)[-1].lower() if "." in en.name else ""
        info = dict(name=en.name, size=fmt_size(en.size),
                    date=en.mtime.strftime("%d/%m/%Y") if en.mtime else "", kind="info",
                    text="", source="")
        self._preview_serial += 1
        if ext in IMAGE_TYPES and 0 < en.size <= PREVIEW_IMAGE_LIMIT:
            info.update(kind="image")       # its picture arrives when it has been read
            serial, session = self._preview_serial, self._session
            target = os.path.join(self._preview_dir, f"{serial}.{ext}")

            def load():
                with open(target, "wb") as out:
                    out.write(session.read_file(en, PREVIEW_IMAGE_LIMIT))
                self._events.put(("preview", (serial, target)))

            self._run(load)
        elif en.size:
            head = self._session.read_file(en, PREVIEW_TEXT_LIMIT)
            if looks_text(head):
                info.update(kind="text", text=head.decode("utf-8", "replace"))
        self._set(preview=info)

    @Slot(bool)
    def setWithOrphans(self, value):
        self._set(withOrphans=value)

    @Slot()
    def openDestination(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._s["destPath"]))

    @Slot()
    def openReport(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._s["reportPath"]))
