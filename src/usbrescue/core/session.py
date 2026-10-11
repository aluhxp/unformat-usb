"""One recovery job: scan a source, then recover from it.

Both steps are generators of events (see model.py), so a command line or a
window can show what is happening while it happens."""

import os
import stat

from . import fat32
from .boot import read_boot
from .clues import name_clues
from .exfat import ExfatTree
from .model import (CopyProgress, FileRecovered, FolderFound, GeometryCalibrated, Names,
                    NothingFound, OrphanRecovered, RecoverFinished, ScanFinished,
                    ScanProgress, ScanResult, SourceOpened, TreeReset)
from .oldfat import to_runs
from .orphans import COPY_BLOCK, find_orphans, save_orphan
from .reader import Source
from .scan import scan_blocks
from .tree import build_paths
from .util import sanitize


class UnsafeDestination(Exception):
    """The destination is on the device being recovered."""


def _whole_disk(dev):
    """Name of the disk a Linux device number belongs to (sdb1 -> sdb)."""
    node = os.path.realpath(f"/sys/dev/block/{os.major(dev)}:{os.minor(dev)}")
    if os.path.exists(os.path.join(node, "partition")):
        node = os.path.dirname(node)
    return os.path.basename(node)


def check_destination(source_path, dest):
    """Writing recovered files onto the source would destroy what is left."""
    try:
        src = os.stat(source_path)
    except OSError:
        return
    if not stat.S_ISBLK(src.st_mode):
        return
    probe = os.path.abspath(dest)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    if _whole_disk(os.stat(probe).st_dev) == _whole_disk(src.st_rdev):
        raise UnsafeDestination(dest)


def iter_runs(disk, g, runs, nbytes):
    remaining = nbytes
    for first, count in runs:
        pos, left = g.coff(first), min(remaining, count * g.cs)
        while left > 0:
            data = disk.read(pos, min(left, COPY_BLOCK))
            if not data:
                return
            yield data
            pos += len(data)
            left -= len(data)
            remaining -= len(data)
        if remaining <= 0:
            return


class Session:
    def __init__(self, source_path, *, include_deleted=False, fs_type=None,
                 find_orphans=True, names=None):
        self.source_path = source_path
        self.disk = Source(source_path)
        self.include_deleted = include_deleted
        self.fs_type = fs_type
        self.find_orphans = find_orphans
        self.names = names or Names()
        self.result = None

    def close(self):
        self.disk.close()

    # ---------------------------------------------------------------- scan

    def scan(self):
        disk, deleted = self.disk, self.include_deleted
        boot = read_boot(disk)
        yield SourceOpened(disk.size, boot["fs"] if boot else None)

        dots, refs = [], []
        live = ExfatTree(disk, boot, deleted)
        announced = False
        for hit in scan_blocks(disk, deleted):
            kind = hit[0]
            if kind == "ex_start":
                live.add_start(hit[1])
            elif kind == "ex_root":
                live.add_root(hit[1])
            elif kind == "fat_dot":
                dots.append(hit[1:])
            elif kind == "fat_ref":
                refs.append(hit[1:])
            else:
                if self.fs_type != "fat32":
                    for ev in live.checkpoint(hit[1]):
                        announced = True
                        yield ev
                yield ScanProgress(hit[1], disk.size)

        fs = self.fs_type or ("fat32" if dots and len(dots) >= len(live.starts) / 4 else "exfat")
        if fs == "fat32" and dots:
            if announced:
                yield TreeReset()
            g, parent_of, contents, root_ents, dir_cls, root_cl, calibration = \
                fat32.build_tree(disk, dots, refs, boot, deleted)
            blocks = len(dots)
            yield GeometryCalibrated("fat32", g.cs, g.start, False)
            for c, ents in contents.items():
                files = [en for en in ents if not en.is_dir]
                yield FolderFound(c, parent_of.get(c), None, len(files),
                                  sum(en.size for en in files))
        elif fs == "exfat" and live.starts:
            yield from live.finish()
            if live.geometry is None:
                yield NothingFound()
                return
            g, parent_of, contents, dir_cls = live.geometry, live.parent_of, live.contents, live.dir_cls
            root_ents, root_cl = live.root_entries, live.root_cluster
            calibration, blocks = live.calibration, len(live.starts)
        else:
            yield NothingFound()
            return

        paths, known = build_paths(parent_of, contents, root_ents, root_cl, self.names)
        tasks = [(paths[c], en) for c, ents in contents.items() for en in ents if not en.is_dir]
        tasks += [("", en) for en in root_ents if not en.is_dir]
        total = sum(en.size for _, en in tasks)

        plans, claimed, frag, chained = self._make_plans(g, g.fat, tasks, dir_cls, boot)
        fat_state = "missing"
        if g.fat and frag and chained * 2 < frag:
            fat_state = "unreliable"
            g.fat = None
            plans, claimed, frag, chained = self._make_plans(g, None, tasks, dir_cls, boot)
        elif g.fat:
            fat_state = "kept"

        unnamed = {c: p for c, p in paths.items() if c not in known and os.sep not in p}
        orphans, renamed = [], {}
        if fs == "exfat" and self.find_orphans:
            orphans = find_orphans(disk, g, claimed)
            renamed = name_clues(disk, g, orphans, contents, unnamed)

            def new_path(rel):
                top, sep, rest = rel.partition(os.sep)
                return renamed[top] + sep + rest if top in renamed else rel

            plans = [(new_path(rel), en, runs, method) for rel, en, runs, method in plans]
            paths = {c: new_path(p) for c, p in paths.items()}

        self.result = ScanResult(
            fs=fs, geometry=g, contents=contents, parent_of=parent_of, dir_clusters=dir_cls,
            paths=paths, plans=plans, total_bytes=total, orphans=orphans, renamed=renamed,
            unnamed_tops=len(unnamed) - len(renamed), calibration=calibration,
            folder_blocks=blocks, fragmented=frag, chained=chained, fat_state=fat_state,
            root_recovered=fs == "exfat" and live.root_is_old,
            names=self.names)
        yield ScanFinished(self.result)

    def _make_plans(self, g, fat, tasks, dir_cls, boot):
        """Which clusters each file comes from. Also notes which clusters
        have an owner, so the orphan search knows where not to look."""
        nclus = max(0, (self.disk.size - g.start) // g.cs)
        plans, claimed, frag, chained = [], bytearray(nclus + 2), 0, 0
        for c in dir_cls:
            if 0 <= c < len(claimed):
                claimed[c] = 1
        if boot and boot["fs"] == "exfat" and (boot["cs"], boot["start"]) == (g.cs, g.start):
            for c in range(2, min(boot["root"] + 1, len(claimed))):
                claimed[c] = 1   # bitmap, upcase table and root of the new format
        for rel, en in tasks:
            ncl = (en.size + g.cs - 1) // g.cs
            runs, method = [(en.cluster, ncl)], "contiguous"
            if en.size and en.cluster >= 2 and not en.contiguous:
                frag += 1
                ch = fat.chain(en.cluster, ncl) if fat else None
                if ch:
                    runs, method = to_runs(ch), "fat_chain"
                    chained += 1
            if en.size and en.cluster >= 2:
                for first, count in runs:
                    a, b = max(first, 0), min(first + count, len(claimed))
                    if b > a:
                        claimed[a:b] = b"\x01" * (b - a)
            plans.append((rel, en, runs, method))
        return plans, claimed, frag, chained

    # ------------------------------------------------------------- recover

    def recover(self, dest, *, only_orphans=False, folders=None, with_orphans=True):
        """folders: relative folder paths to recover (None = all of them)."""
        r, disk = self.result, self.disk
        g = r.geometry
        check_destination(self.source_path, dest)
        os.makedirs(dest, exist_ok=True)
        done, ok, warned = 0, 0, 0
        taken = set()
        plans = [] if only_orphans else r.plans
        if folders is not None:
            plans = [p for p in plans if p[0] in folders]
        total = sum(p[1].size for p in plans)
        orphans = r.orphans if with_orphans else []
        for rel, en, runs, method in plans:
            folder = os.path.join(dest, rel)
            os.makedirs(folder, exist_ok=True)
            fname = sanitize(en.name)
            target = os.path.join(folder, fname)
            n = 1
            while target.lower() in taken or os.path.exists(target):
                base, ext = os.path.splitext(fname)
                target = os.path.join(folder, f"{base} ({n}){ext}")
                n += 1
            taken.add(target.lower())

            warnings = []
            if en.size and en.cluster < 2:
                warnings.append("no_data")
            elif en.size and method == "contiguous":
                ncl = (en.size + g.cs - 1) // g.cs
                if any((en.cluster + k) in r.dir_clusters for k in range(min(ncl, 1 << 20))):
                    warnings.append("fragmented")
                elif not en.contiguous:
                    warnings.append("maybe_fragmented")
                if g.coff(en.cluster) + en.size > disk.size:
                    warnings.append("incomplete")
            if en.deleted:
                warnings.append("was_deleted")

            valid = en.size if en.valid is None else min(en.valid, en.size)
            bad_before = disk.bad_sectors
            with open(target, "wb") as out:
                if en.cluster >= 2:
                    for data in iter_runs(disk, g, runs, valid):
                        out.write(data)
                        done += len(data)
                        yield CopyProgress(done, total)
                if en.size > valid:
                    out.truncate(en.size)
            if disk.bad_sectors > bad_before:
                warnings.append("bad_sectors")
            if en.mtime:
                try:
                    ts = en.mtime.timestamp()
                    os.utime(target, (ts, ts))
                except (OverflowError, OSError, ValueError):
                    pass
            ok += not warnings
            warned += bool(warnings)
            yield FileRecovered(os.path.relpath(target, dest), en.size, en.mtime, warnings, method)

        saved = 0
        if orphans:
            folder = os.path.join(dest, r.names.orphan_dir)
            os.makedirs(folder, exist_ok=True)
            for o in orphans:
                res = save_orphan(disk, g, o, folder, r.names.orphan_file)
                if res:
                    path, size, when, status = res
                    saved += 1
                    yield OrphanRecovered(os.path.relpath(path, dest), size, when, status, o.method)
        yield RecoverFinished(ok, warned, saved, len(orphans), disk.bad_sectors)
