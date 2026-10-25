"""One recovery job: scan a source, then recover from it.

Both steps are generators of events (see model.py), so a command line or a
window can show what is happening while it happens."""

import hashlib
import os
import stat

from . import fat32, ntfs, rawdisk
from .boot import read_boot
from .clues import name_clues
from .exfat import ExfatTree
from .inuse import clusters_in_use
from .kinds import MEDIA, is_media
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
    if rawdisk.is_windows_drive(source_path):
        number = rawdisk.windows_disk_number(source_path)
        if number is not None and number in rawdisk.windows_disks_of_folder(dest):
            raise UnsafeDestination(dest)
        return
    if rawdisk.is_mac_disk(source_path):
        _check_mac_destination(source_path, dest)
        return
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


def _check_mac_destination(source_path, dest):
    """/dev/rdisk4 or /dev/disk4s1 against the disk the folder is on."""
    import plistlib
    import re
    import subprocess
    disk = re.sub(r"^r", "", os.path.basename(source_path))
    disk = re.match(r"disk\d+", disk).group(0)
    probe = os.path.abspath(dest)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    try:
        info = plistlib.loads(subprocess.run(["diskutil", "info", "-plist", probe],
                                             capture_output=True, timeout=10).stdout)
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException):
        return
    if info.get("ParentWholeDisk") == disk:
        raise UnsafeDestination(dest)


def iter_runs(disk, g, runs, nbytes):
    remaining = nbytes
    for first, count in runs:
        pos, left = g.coff(first), min(remaining, count * g.cs)
        while left > 0:
            if first < 0:                   # nothing stored here (NTFS): zeros
                data = b"\x00" * min(left, COPY_BLOCK)
            else:
                data = disk.read(pos, min(left, COPY_BLOCK))
            if not data:
                return
            yield data
            pos += len(data)
            left -= len(data)
            remaining -= len(data)
        if remaining <= 0:
            return


def file_chunks(disk, g, en, runs, nbytes):
    """The first nbytes of a file's content, a block at a time."""
    if en.data is not None:                 # kept inside its NTFS record
        if nbytes:
            yield en.data[:nbytes]
    elif en.cluster < 2:
        return
    elif en.compressed:
        yield from ntfs.iter_compressed(disk, g, runs, nbytes, en.compressed)
    else:
        yield from iter_runs(disk, g, runs, nbytes)


def _mostly_inside(recs, g, contents, root_ents):
    """Do most of these NTFS records lie inside files of the other file system?"""
    import bisect
    spans = sorted((g.coff(en.cluster), g.coff(en.cluster) + en.size)
                   for ents in list(contents.values()) + [root_ents or []] for en in ents
                   if not en.is_dir and en.size and en.cluster >= 2)
    starts = [a for a, _ in spans]
    reach, ends = 0, []
    for _, b in spans:                      # how far the files up to each one reach
        reach = max(reach, b)
        ends.append(reach)
    inside = 0
    for r in recs:
        i = bisect.bisect_right(starts, r.off) - 1
        inside += i >= 0 and r.off < ends[i]
    return inside * 2 > len(recs)


def file_key(en):
    """Identifies a file across re-reads of its folder."""
    return (en.cluster, en.size, en.name)


def file_plan(en, g, fat):
    """(runs, method): the clusters a file's data comes from."""
    if en.data is not None:
        return [], "ntfs_resident"
    if en.runs is not None:
        return en.runs, "ntfs_runs"
    ncl = (en.size + g.cs - 1) // g.cs
    if en.size and en.cluster >= 2 and not en.contiguous and fat:
        chain = fat.chain(en.cluster, ncl)
        if chain:
            return to_runs(chain), "fat_chain"
    return [(en.cluster, ncl)], "contiguous"


class Session:
    def __init__(self, source_path, *, include_deleted=False, fs_type=None,
                 find_orphans=True, names=None, disk=None):
        """include_deleted: False, True, or "only" (just the files that were
        deleted, in their folders: for a drive that was not formatted)."""
        self.source_path = source_path
        self.disk = disk or Source(source_path)
        self.include_deleted = include_deleted
        self.fs_type = fs_type
        self.find_orphans = find_orphans
        self.names = names or Names()
        self.result = None
        self.live = None        # the exFAT tree while it is being built
        self._in_use = False    # clusters the current file system uses (looked up once)

    def close(self):
        self.disk.close()

    # ---------------------------------------------------------------- scan

    def scan(self):
        disk, deleted = self.disk, self.include_deleted
        boot = read_boot(disk)
        yield SourceOpened(disk.size, boot["fs"] if boot else None)

        dots, refs = [], []
        live = self.live = ExfatTree(disk, boot, deleted)
        nt = ntfs.NtfsTree(disk, boot, deleted)
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
            elif kind == "ntfs_rec":
                nt.add(hit[2], hit[1])
            else:
                if self.fs_type not in ("fat32", "ntfs"):
                    for ev in live.checkpoint(hit[1]):
                        announced = True
                        yield ev
                yield ScanProgress(hit[1], disk.size)

        fs = self.fs_type or self._pick_fs(boot, dots, live, nt)
        own = labels = fat_tree = None
        finished = False
        if fs == "ntfs" and not self.fs_type and (dots or live.starts):
            # an NTFS disk image kept as a file on a FAT32/exFAT drive holds
            # records too: they don't make the drive NTFS
            if dots and len(dots) >= len(live.starts) / 4:
                other = "fat32"
                fat_tree = fat32.build_tree(disk, dots, refs, boot, deleted)
                g0, contents0, root0 = fat_tree[0], fat_tree[2], fat_tree[3]
            else:
                other = "exfat"
                for ev in live.finish():
                    announced = True
                    yield ev
                finished = True
                g0, contents0, root0 = live.geometry, live.contents, live.root_entries
            if g0 is not None and _mostly_inside(nt.recs, g0, contents0, root0):
                fs = other
        if fs == "ntfs" and nt.recs:
            if announced:
                yield TreeReset()
            g, parent_of, contents, root_ents, dir_cls, calibration, own, labels = nt.build(self.names)
            if not contents and not root_ents:
                yield NothingFound()
                return
            root_cl, blocks = ntfs.ROOT, len(nt.recs)
            yield GeometryCalibrated("ntfs", g.cs, g.start, False)
            for c, ents in contents.items():
                files = [en for en in ents if not en.is_dir]
                yield FolderFound(c, parent_of.get(c), own.get(c), len(files),
                                  sum(en.size for en in files))
        elif fs == "fat32" and dots:
            if announced:
                yield TreeReset()
            g, parent_of, contents, root_ents, dir_cls, root_cl, calibration = \
                fat_tree or fat32.build_tree(disk, dots, refs, boot, deleted)
            blocks = len(dots)
            yield GeometryCalibrated("fat32", g.cs, g.start, False)
            for c, ents in contents.items():
                files = [en for en in ents if not en.is_dir]
                yield FolderFound(c, parent_of.get(c), None, len(files),
                                  sum(en.size for en in files))
        elif fs == "exfat" and live.starts:
            if not finished:
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

        paths, known = build_paths(parent_of, contents, root_ents, root_cl, self.names, own, labels)
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

        if deleted == "only" or fs == "ntfs":
            # the live files are not listed, but their space is not free:
            # the search for loose files must not bring them back (on NTFS
            # that includes the new format's own files)
            in_use = clusters_in_use(disk, boot, g)
            if in_use:
                in_use.mark(claimed)
        unnamed = {c: p for c, p in paths.items() if c not in known and os.sep not in p}
        orphans, renamed = [], {}
        if fs in ("exfat", "ntfs") and self.find_orphans:
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
            root_recovered=(fs == "exfat" and live.root_is_old) or (fs == "ntfs" and bool(root_ents)),
            names=self.names)
        yield ScanFinished(self.result)

    @staticmethod
    def _pick_fs(boot, dots, live, nt):
        """Which old file system the drive holds the most of. NTFS counts
        files and folders, the others count folders."""
        folders = len(dots) if dots and len(dots) >= len(live.starts) / 4 else len(live.starts)
        if nt.recs:
            nt_folders, nt_files = nt.count()
            if nt_files and ((nt.deleted == "only" and boot and boot["fs"] == "ntfs")
                             or nt_folders + nt_files / 8 > folders):
                return "ntfs"
        return "fat32" if dots and len(dots) >= len(live.starts) / 4 else "exfat"

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
            runs, method = file_plan(en, g, fat)
            if en.size and en.cluster >= 2 and not en.contiguous:
                frag += 1
                chained += method == "fat_chain"
            if en.size and en.cluster >= 2:
                for first, count in runs:
                    if first < 0:
                        continue
                    a, b = first, min(first + count, len(claimed))
                    if b > a:
                        claimed[a:b] = b"\x01" * (b - a)
            plans.append((rel, en, runs, method))
        return plans, claimed, frag, chained

    def _space_reused(self, g, runs):
        """Is a deleted file's space used by the current file system?"""
        if self._in_use is False:
            self._in_use = clusters_in_use(self.disk, read_boot(self.disk), g)
        return bool(self._in_use) and self._in_use.any(runs)

    # ------------------------------------------- looking before recovering

    @property
    def geometry(self):
        if self.result:
            return self.result.geometry
        return self.live.geometry if self.live else None

    def folder_files(self, cluster):
        """Files directly inside a folder; works while the scan is running."""
        contents = self.result.contents if self.result else (self.live.contents if self.live else {})
        return [en for en in contents.get(cluster, []) if not en.is_dir]

    def read_file(self, en, limit):
        """The first `limit` bytes of a file, for a preview."""
        g = self.geometry
        if g is None or not en.size:
            return b""
        runs, _ = file_plan(en, g, g.fat)
        valid = en.size if en.valid is None else min(en.valid, en.size)
        return b"".join(file_chunks(self.disk, g, en, runs, min(valid, limit)))[:limit]

    def live_plans(self, clusters):
        """Plans for folders picked while the scan is still running. A folder
        whose parents are not known yet goes under the names known so far."""
        live, g = self.live, self.geometry
        if live is None or g is None:
            return []

        def path_of(c):
            parts, seen = [], set()
            while c and c not in seen:
                seen.add(c)
                name = live._names.get(c)
                parts.append(sanitize(name) if name else self.names.unnamed_folder.format(c))
                c = live.parent_of.get(c)
            return os.path.join(*reversed(parts))

        return [(path_of(c), en) + file_plan(en, g, g.fat)
                for c in clusters for en in self.folder_files(c)]

    # ------------------------------------------------------------- recover

    def recover(self, dest, *, only_orphans=False, folders=None, with_orphans=True,
                skip=None, plans=None, only_media=False):
        """folders: relative folder paths to recover (None = all of them).
        skip: file keys to leave out. plans: recover exactly these instead,
        which is how folders are rescued before the scan ends.
        only_media: just photos and videos, each still in its own folder."""
        r, disk, g = self.result, self.disk, self.geometry
        dir_clusters = r.dir_clusters if r else self.live.dir_cls
        check_destination(self.source_path, dest)
        os.makedirs(dest, exist_ok=True)
        done, ok, warned = 0, 0, 0
        taken = set()
        if plans is None:
            plans = [] if only_orphans else r.plans
            orphans = r.orphans if with_orphans else []
        else:
            orphans = []
        if folders is not None:
            plans = [p for p in plans if p[0] in folders]
        if skip:
            plans = [p for p in plans if file_key(p[1]) not in skip]
        if only_media:
            plans = [p for p in plans if is_media(p[1].name)]
            orphans = [o for o in orphans if o.ext in MEDIA]
        total = sum(p[1].size for p in plans)
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
            if en.size and en.cluster < 2 and en.data is None:
                warnings.append("no_data")
            elif method == "ntfs_runs":
                stored = sum(n for _, n in runs) * g.cs
                if (not en.compressed and stored < en.size) or \
                        any(first >= 0 and g.coff(first + n) > disk.size for first, n in runs):
                    warnings.append("incomplete")
                if en.encrypted:
                    warnings.append("encrypted")
            elif en.size and method == "contiguous":
                ncl = (en.size + g.cs - 1) // g.cs
                if any((en.cluster + k) in dir_clusters for k in range(min(ncl, 1 << 20))):
                    warnings.append("fragmented")
                elif not en.contiguous:
                    warnings.append("maybe_fragmented")
                if g.coff(en.cluster) + en.size > disk.size:
                    warnings.append("incomplete")
            if en.deleted:
                if self.include_deleted != "only":     # there, every file was deleted
                    warnings.append("was_deleted")
                if en.size and en.cluster >= 2 and self._space_reused(g, runs):
                    en.overwritten = True
                    warnings.append("overwritten")

            valid = en.size if en.valid is None else min(en.valid, en.size)
            bad_before = disk.bad_sectors
            with open(target, "wb") as out:
                if en.cluster >= 2 or en.data is not None:
                    for data in file_chunks(disk, g, en, runs, valid):
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

        saved, duplicate = 0, 0
        if orphans:
            folder = os.path.join(dest, self.names.orphan_dir)
            os.makedirs(folder, exist_ok=True)
            twins = _Twins(self)
            found, covered_to = len(orphans), 0
            for o in orphans:               # in disk order
                if o.size is not None and o.cluster < covered_to:
                    # text inside a file just rescued by its signature (the
                    # readable tail of a PDF, say): part of that file, not a new one
                    found -= 1
                    continue
                res = save_orphan(disk, g, o, folder, self.names)
                if res:
                    path, size, when, status = res
                    if not o.exact and status in ("verified", "pdf_valid", "png_complete"):
                        # only a file whose end is known for sure covers what follows it
                        covered_to = max(covered_to, o.cluster + (size + g.cs - 1) // g.cs)
                    if twins.seen_before(path, size):
                        os.remove(path)     # the same file is already among the rescued
                        duplicate += 1
                        continue
                    saved += 1
                    yield OrphanRecovered(os.path.relpath(path, dest), size, when, status, o.method)
        else:
            found = 0
        yield RecoverFinished(ok, warned, saved, found, disk.bad_sectors, duplicate)


def _hash_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(COPY_BLOCK), b""):
            h.update(block)
    return h.digest()


class _Twins:
    """Spots a file without a folder that is a copy of one already known: a
    file in a folder, or an earlier file without one. Sizes are compared
    first, so content is only read when two files could really be the same."""

    def __init__(self, session):
        self.session = session
        self.by_size = {}                   # size -> [entry of a file in a folder]
        for _, en, _, _ in session.result.plans:
            if en.size and en.cluster >= 2:
                self.by_size.setdefault(en.size, []).append(en)
        self.known = {}                     # entry key -> digest
        self.loose = {}                     # size -> {digest or None: path}

    def _hash_entry(self, en):
        key = file_key(en)
        if key not in self.known:
            s = self.session
            g = s.geometry
            runs, _ = file_plan(en, g, g.fat)
            valid = en.size if en.valid is None else min(en.valid, en.size)
            h, got = hashlib.sha1(), 0
            for block in file_chunks(s.disk, g, en, runs, valid):
                h.update(block)
                got += len(block)
            h.update(b"\x00" * (en.size - got))    # the rest of the file is zeros
            self.known[key] = h.digest()
        return self.known[key]

    def seen_before(self, path, size):
        if not size:
            return False
        in_folders = self.by_size.get(size, [])
        earlier = self.loose.setdefault(size, {})
        if not in_folders and not earlier:
            earlier[None] = path            # nothing of this size yet: no need to read it
            return False
        digest = _hash_file(path)
        if None in earlier:                 # the earlier one of this size was never read
            first = earlier.pop(None)
            earlier[_hash_file(first)] = first
        if digest in earlier or any(self._hash_entry(en) == digest for en in in_folders):
            return True
        earlier[digest] = path
        return False
