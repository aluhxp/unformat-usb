"""Safety copy: the whole drive into a file on this computer, before anything
else. A failing drive may not survive being read twice, so the rescue then
works on the copy.

Like ddrescue, it grabs everything that reads easily first and only then
goes back for the hard parts, sector by sector. A small map file next to the
image records what is done, so an interrupted copy picks up where it stopped."""

import hashlib
import json
import os
import shutil
from dataclasses import dataclass

from .session import check_destination
from .util import SECTOR

BLOCK = 1024 * 1024
SAVE_EVERY = 64 * 1024 * 1024


@dataclass
class ImageProgress:
    done: int               # bytes settled so far (read, or given up on)
    total: int
    bad_bytes: int          # bytes that could not be read
    retrying: bool          # second pass, over the parts that failed at first


@dataclass
class ImageFinished:
    path: str
    total: int
    bad_bytes: int


def space_check(size, folder):
    """(free bytes, fits the copy, fits the copy and what is rescued from it)."""
    probe = os.path.abspath(folder)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    free = shutil.disk_usage(probe).free
    return free, free >= size + SAVE_EVERY, free >= 2 * size


def map_path_of(image_path):
    return image_path + ".map"


def _fingerprint(disk):
    """Tells one drive from another of the same size."""
    return hashlib.sha1(disk.read(0, 64 * 1024)).hexdigest()


def _load_map(path, size, drive):
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        if m.get("size") == size and m.get("drive") == drive:
            return m
    except (OSError, ValueError):
        pass
    return {"size": size, "drive": drive, "position": 0, "pending": [], "bad": [], "finished": False}


def _save_map(path, m):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f)
    os.replace(tmp, path)


def _span(runs):
    return sum(n for _, n in runs)


def _add(runs, start, length):
    if runs and runs[-1][0] + runs[-1][1] == start:
        runs[-1][1] += length
    else:
        runs.append([start, length])


def make_image(disk, source_path, image_path):
    """Generator of ImageProgress, ending with ImageFinished. Stop consuming
    it to pause: the map is saved, and calling again resumes."""
    check_destination(source_path, os.path.dirname(os.path.abspath(image_path)))
    size = disk.size
    map_path = map_path_of(image_path)
    m = _load_map(map_path if os.path.exists(image_path) else "", size, _fingerprint(disk))
    if m["finished"]:
        yield ImageFinished(image_path, size, _span(m["bad"]))
        return

    with open(image_path, "r+b" if os.path.exists(image_path) else "w+b") as out:
        out.truncate(size)
        unsaved = 0
        try:
            # first pass: big blocks; whatever fails is left for later
            while m["position"] < size:
                pos = m["position"]
                n = min(BLOCK, size - pos)
                try:
                    data = disk._raw(pos, n)
                except OSError:
                    data = None
                if data is not None and len(data) == n:
                    out.seek(pos)
                    out.write(data)
                else:
                    _add(m["pending"], pos, n)
                m["position"] = pos + n
                unsaved += n
                if unsaved >= SAVE_EVERY:
                    out.flush()
                    _save_map(map_path, m)
                    unsaved = 0
                yield ImageProgress(m["position"] - _span(m["pending"]), size, _span(m["bad"]), False)

            # second pass: the failed blocks again, one sector at a time
            while m["pending"]:
                start, length = m["pending"][0]
                n = min(SECTOR, length)
                try:
                    data = disk._raw(start, n)
                except OSError:
                    data = None
                if data is not None and len(data) == n:
                    out.seek(start)
                    out.write(data)
                else:
                    _add(m["bad"], start, n)
                if length > n:
                    m["pending"][0] = [start + n, length - n]
                else:
                    m["pending"].pop(0)
                unsaved += n
                if unsaved >= BLOCK:
                    _save_map(map_path, m)
                    unsaved = 0
                    yield ImageProgress(size - _span(m["pending"]), size, _span(m["bad"]), True)
            m["finished"] = True
        finally:
            out.flush()
            os.fsync(out.fileno())
            _save_map(map_path, m)
    yield ImageFinished(image_path, size, _span(m["bad"]))
