"""Data shared by every stage, and the events the engine emits."""

from dataclasses import dataclass, field


class Entry:
    """A file or folder as described by a directory entry."""

    __slots__ = ("name", "is_dir", "cluster", "size", "valid", "mtime",
                 "deleted", "contiguous")

    def __init__(self):
        self.valid = None
        self.contiguous = True
        self.deleted = False


class Geometry:
    """Cluster size and where the data area starts, as they were before the format."""

    def __init__(self, cs, start):
        self.cs, self.start = cs, start
        self.fat = None   # old FAT, if it survived (exFAT only)

    def coff(self, c):
        return self.start + (c - 2) * self.cs

    def cluster_of(self, off):
        return (off - self.start) // self.cs + 2


@dataclass
class Names:
    """User-visible names the engine has to invent. The UI supplies its own."""

    unnamed_folder: str = "UNNAMED_FOLDER_{}"
    lost_parent: str = "_LOST_PARENT"
    orphan_dir: str = "_ROOT_AND_ORPHANS"
    orphan_file: str = "orphan_{}"


# ---------------------------------------------------------------- events

@dataclass
class SourceOpened:
    size: int
    current_fs: str | None      # file system written by the format, if recognised


@dataclass
class ScanProgress:
    done: int
    total: int


@dataclass
class GeometryCalibrated:
    fs: str
    cluster_size: int
    data_start: int
    old_fat: bool


@dataclass
class FolderFound:
    """A folder was read. parent is None while its place is still unknown."""
    cluster: int
    parent: int | None
    name: str | None
    files: int
    size: int


@dataclass
class FolderPlaced:
    """A folder found earlier now has a parent (0 = top level, name lost)."""
    cluster: int
    parent: int
    name: str | None


@dataclass
class TreeReset:
    """Folders announced so far were a false lead; the tree starts over."""


@dataclass
class NothingFound:
    pass


@dataclass
class ScanFinished:
    result: "ScanResult"


@dataclass
class FileRecovered:
    path: str                   # relative to the destination
    size: int
    mtime: object
    warnings: list
    method: str


@dataclass
class OrphanRecovered:
    path: str
    size: int
    mtime: object
    status: str
    method: str


@dataclass
class CopyProgress:
    done: int
    total: int


@dataclass
class RecoverFinished:
    ok: int
    warned: int
    orphans_saved: int
    orphans_found: int
    bad_sectors: int


@dataclass
class ScanResult:
    fs: str
    geometry: Geometry
    contents: dict              # folder cluster -> [Entry]
    parent_of: dict
    dir_clusters: dict          # cluster -> folder that owns it
    paths: dict                 # folder cluster -> relative path
    plans: list                 # (relative folder, Entry, runs, method)
    total_bytes: int
    orphans: list
    renamed: dict               # unnamed top folder -> original name found by a clue
    unnamed_tops: int
    calibration: tuple          # (matching references, references checked)
    folder_blocks: int
    fragmented: int             # files whose entry says they are not contiguous
    chained: int                # ...of which the old FAT has the full chain
    fat_state: str              # "kept" | "unreliable" | "missing"
    names: Names = field(default_factory=Names)
