"""Names for folders that lost theirs in the format.

Two ways, in this order:
  1. The original name, given away by a path stored inside some file:
     an Office document remembers 'E:\\Work\\Reports\\' when it was saved,
     a shortcut or a playlist holds full paths, a note may quote one. If the
     part after a folder name matches what an unnamed folder holds
     ('Reports\\budget.xlsx'), that folder was called 'Work'.
  2. Otherwise, a name from what it holds: mostly photos from 2023 make
     'Photos 2023'.

Nothing is renamed here without being asked: suggest() only proposes, and
rename() / undo() do what the person approved, keeping a log to go back."""

import collections
import datetime
import io
import json
import os
import re
import urllib.parse
import zipfile
from dataclasses import dataclass

from .util import sanitize


# ----------------------------------------------------------- what to read

@dataclass
class Item:
    """A rescued file. parts: its path, the folder names and then its own."""
    parts: tuple
    size: int
    mtime: object               # datetime or None
    read: object                # read(limit) -> bytes


def items_from_folder(dest, skip=()):
    """Files already rescued into a folder on this computer. skip: names of
    files at the top that this program wrote itself (report, log)."""
    out = []
    for base, dirs, files in os.walk(dest):
        dirs.sort()
        rel = os.path.relpath(base, dest)
        prefix = () if rel == "." else tuple(rel.split(os.sep))
        for name in sorted(files):
            if not prefix and name in skip:
                continue
            full = os.path.join(base, name)
            try:
                st = os.stat(full)
            except OSError:
                continue

            def read(limit, full=full):
                with open(full, "rb") as fh:
                    return fh.read(limit)

            out.append(Item(prefix + (name,), st.st_size,
                            datetime.datetime.fromtimestamp(st.st_mtime), read))
    return out


def items_from_session(session):
    """Files a scan found, read from the source: lets a suggestion be tried
    without copying anything."""
    out = []
    for rel, en, _, _ in session.result.plans:
        prefix = tuple(p for p in rel.split(os.sep) if p)
        out.append(Item(prefix + (sanitize(en.name),), en.size, en.mtime,
                        lambda limit, en=en: session.read_file(en, limit)))
    return out


def placeholder_pattern(fmt):
    """'Folder {}' -> a regex that matches 'Folder 1234'."""
    return re.compile("^" + re.escape(fmt).replace(r"\{\}", r"\d+") + "$")


def unnamed_folders(items, names):
    """Relative paths of the folders still called by a placeholder: at the
    top, or right under the folder of lost parents."""
    pat = placeholder_pattern(names.unnamed_folder)
    found = set()
    for it in items:
        p = it.parts[:-1]
        if p and pat.match(p[0]):
            found.add(p[:1])
        elif len(p) >= 2 and p[0] == names.lost_parent and pat.match(p[1]):
            found.add(p[:2])
    return sorted(found)


# ------------------------------------------------- paths inside of files

PATH_EXTS = {
    # shortcuts and playlists are lists of paths
    "lnk": 3, "url": 3, "m3u": 3, "m3u8": 3, "pls": 3, "wpl": 3, "xspf": 3, "zpl": 3,
    # Office remembers where it saved, and links to other files
    "xlsx": 2, "xlsm": 2, "docx": 2, "pptx": 2,
    "xls": 2, "doc": 2, "ppt": 2,
    "ini": 1, "inf": 1, "txt": 1, "log": 1, "csv": 1, "htm": 1, "html": 1, "xml": 1,
    "json": 1, "bat": 1, "cmd": 1, "ps1": 1, "sh": 1, "desktop": 1, "reg": 1, "md": 1,
    "srt": 1, "cue": 1, "nfo": 1,
}
READ_LIMIT = 256 * 1024
OFFICE_LIMIT = 8 * 1024 * 1024
MAX_FILES = 6000
MAX_BYTES = 400 * 1024 * 1024

_SEG = r"[^\x00-\x1f\\/:*?\"<>|]{1,120}"
_WIN = re.compile(r"(?:\b[A-Za-z]:|\\\\" + _SEG + r")((?:\\" + _SEG + r")+)\\?")
_URL = re.compile(r"file:/{2,3}(?:[A-Za-z](?::|%3A)|localhost)?((?:/[^\s\"'<>]{1,120})+)", re.I)
_UNIX = re.compile(r"(?<![\w.~/:])((?:/[\w .,()&'+\-\[\]~#@!%\u00c0-\uffff]{1,120}){2,})")
_REL = re.compile(r"^\s*(?:\.\.?[\\/])*((?:[^\x00-\x1f\\/:*?\"<>|#]{1,120}[\\/])+[^\x00-\x1f\\/:*?\"<>|]{1,120})\s*$",
                  re.M)


def _texts(data):
    """Ways the bytes may hold text: 8-bit, and UTF-16 (Windows) at both alignments."""
    yield data.decode("latin-1")
    if data.count(b"\x00") * 8 > len(data):
        for start in (0, 1):
            yield data[start:len(data) - (len(data) - start) % 2].decode("utf-16-le", "replace")


def _fix(text):
    """Office and the web store UTF-8 inside text read as Latin-1."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _office_text(data):
    """The XML parts of an Office file, where its paths are."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            chunks, total = [], 0
            for info in z.infolist():
                name = info.filename
                if not name.endswith((".xml", ".rels")) or info.file_size > 4 * 1024 * 1024:
                    continue
                if name.startswith(("word/document", "xl/sharedStrings", "xl/worksheets",
                                    "ppt/slides/slide", "word/media", "xl/media")):
                    continue            # the text itself: long, and not where paths are kept
                chunks.append(z.read(info).decode("utf-8", "replace"))
                total += info.file_size
                if total > 16 * 1024 * 1024:
                    break
            return "\n".join(chunks)
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, NotImplementedError, EOFError):
        return ""


def paths_in(data, ext):
    """Every path a file holds, each as a list of names (drive letter left out)."""
    out = []
    if ext in ("xlsx", "xlsm", "docx", "pptx") and data[:2] == b"PK":
        texts = [_office_text(data)]
    else:
        texts = list(_texts(data))
    for text in texts:
        for m in _WIN.finditer(text):
            out.append([_fix(x) for x in m.group(1).split("\\") if x])
        for m in _URL.finditer(text):
            raw = urllib.parse.unquote(m.group(1).replace("\\", "/"))
            out.append([x for x in raw.split("/") if x])
        for m in _UNIX.finditer(text):
            out.append([_fix(x) for x in m.group(1).split("/") if x])
        if ext in ("m3u", "m3u8", "pls", "cue", "wpl", "xspf", "zpl"):
            for m in _REL.finditer(text):
                out.append([_fix(x) for x in re.split(r"[\\/]", m.group(1)) if x and x != ".."])
    clean = []
    for parts in out:
        parts = [p.strip() for p in parts]
        parts = [p for p in parts if p and p not in (".", "..")]
        if len(parts) < 2:
            continue
        clean.append(parts)
        # a path quoted in a sentence runs on into the words after it
        m = re.match(r"(.+?\.[A-Za-z0-9]{2,5})(?=[\s,;)]|$)", parts[-1])
        if m and m.group(1) != parts[-1]:
            clean.append(parts[:-1] + [m.group(1)])
    return clean


# ------------------------------------------------------------ the folders

class _Folder:
    """What an unnamed folder holds, as a tree of lower-case names."""

    def __init__(self, path):
        self.path = path            # tuple: relative path of the folder
        self.tree = {}
        self.items = []

    def add(self, it):
        self.items.append(it)
        node = self.tree
        for name in it.parts[len(self.path):]:
            node = node.setdefault(name.lower(), {})

    def depth(self, rest):
        """How many names of rest, in order, are found going down this folder."""
        node, n = self.tree, 0
        for name in rest:
            node = node.get(name.lower())
            if node is None:
                break
            n += 1
        return n


def _distinctive(name, is_file):
    """A name unlikely to be shared by chance: not 'notes.txt', '1.jpg' or 'Photos'."""
    stem, dot, _ = name.rpartition(".")
    if not is_file or not dot:
        letters = sum(ch.isalpha() for ch in name)
        return letters >= 4 and name.lower() not in GENERIC_DIRS
    letters = sum(ch.isalnum() for ch in stem)
    return letters >= 6 and stem.lower() not in GENERIC_STEMS


GENERIC_STEMS = {"thumbs", "desktop", "readme", "index", "default", "document", "documento",
                 "untitled", "sin titulo", "nuevo", "new", "image", "imagen", "notas", "notes"}
GENERIC_DIRS = {"nueva carpeta", "new folder", "fotos", "photos", "imagenes", "images", "videos",
                "musica", "music", "documentos", "documents", "descargas", "downloads", "desktop",
                "escritorio", "varios", "misc", "otros", "backup", "respaldo", "copia", "temp",
                "nuevo", "new", "files", "archivos", "dcim", "camera", "data", "datos"}
SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", "folder.jpg", "albumartsmall.jpg"}


def _original_names(folders, items, taken, budget):
    """{folder path: (name, score, example)} from paths found inside files."""
    candidates = [it for it in items if it.size and it.parts[-1].rpartition(".")[2].lower() in PATH_EXTS]
    candidates.sort(key=lambda it: -PATH_EXTS[it.parts[-1].rpartition(".")[2].lower()])
    scores = {f.path: collections.Counter() for f in folders}
    spelled = {}                    # lower-case name -> as first written
    examples = {}
    read_bytes = 0
    for it in candidates[:budget["files"]]:
        ext = it.parts[-1].rpartition(".")[2].lower()
        limit = OFFICE_LIMIT if ext in ("xlsx", "xlsm", "docx", "pptx") else READ_LIMIT
        if read_bytes > budget["bytes"]:
            break
        try:
            data = it.read(limit)
        except OSError:
            continue
        read_bytes += len(data)
        seen = set()
        for parts in paths_in(data, ext):
            key = tuple(p.lower() for p in parts)
            if key in seen:
                continue                # one file repeating a path is one piece of evidence
            seen.add(key)
            for f in folders:
                best, best_i = 0, None
                for i in range(len(parts) - 1):
                    d = f.depth(parts[i + 1:])
                    if d > best:
                        best, best_i = d, i
                if best_i is None:
                    continue
                name, rest = parts[best_i], parts[best_i + 1:]
                matched = rest[:best]
                # a file saying where it is itself (Excel does) is the best witness
                here = [p.lower() for p in it.parts[len(f.path):-1]]
                own = it.parts[:len(f.path)] == f.path and \
                    [p.lower() for p in matched] == here[:len(matched)]
                if best == 1 and not own and not _distinctive(matched[0], len(rest) == 1):
                    continue            # one shared, common name proves nothing
                if re.fullmatch(r"[A-Za-z]:|[A-Za-z]\$", name) or name.lower() in taken:
                    continue
                low = name.lower()
                spelled.setdefault(low, name)
                scores[f.path][low] += 2 if best >= 2 or own else 1
                examples.setdefault((f.path, low), os.sep.join(parts))
    found = {}
    for path, counter in scores.items():
        ranked = counter.most_common(2)
        if not ranked:
            continue
        low, score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        if score >= 2 and score >= 2 * runner_up:
            found[path] = (spelled[low], score, examples[(path, low)])
    return found


# ----------------------------------------------------- names from content

KINDS = {
    "photos": ("jpg", "jpeg", "png", "heic", "heif", "gif", "bmp", "webp", "tif", "tiff", "raw",
               "cr2", "cr3", "nef", "arw", "dng", "orf", "rw2"),
    "videos": ("mp4", "mkv", "avi", "mov", "wmv", "3gp", "mpg", "mpeg", "m4v", "webm", "flv", "vob",
               "mts", "m2ts"),
    "music": ("mp3", "wav", "flac", "m4a", "ogg", "wma", "aac", "opus", "mid", "midi", "amr"),
    "documents": ("doc", "docx", "odt", "pdf", "rtf", "txt", "md", "pages"),
    "spreadsheets": ("xls", "xlsx", "xlsm", "ods", "csv", "numbers"),
    "presentations": ("ppt", "pptx", "pps", "ppsx", "odp", "key"),
    "programs": ("exe", "msi", "apk", "deb", "rpm", "dmg", "pkg", "appimage", "jar"),
    "disk_images": ("iso", "img", "vhd", "vhdx", "vmdk", "wim", "esd"),
    "archives": ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"),
    "code": ("py", "java", "js", "ts", "c", "h", "cpp", "cs", "php", "html", "htm", "css", "sql",
             "kt", "go", "rb", "sh", "ipynb", "json", "xml"),
    "books": ("epub", "mobi", "azw", "azw3", "djvu", "cbr", "cbz"),
    "fonts": ("ttf", "otf", "woff", "woff2"),
}
_KIND_OF = {ext: kind for kind, exts in KINDS.items() for ext in exts}

STOP_WORDS = {
    "img", "dsc", "dscn", "dcim", "pic", "image", "imagen", "imagenes", "photo", "foto", "fotos",
    "video", "videos", "vid", "file", "files", "archivo", "copia", "copy", "documento",
    "document", "documents", "scan", "scanned", "nuevo", "nueva", "new", "final", "untitled",
    "titulo", "version", "screenshot", "captura", "pantalla", "whatsapp", "with", "para", "from",
    "del", "los", "las", "the", "and", "una", "por", "con", "sin", "jpeg", "page", "pagina",
    "track", "pista", "audio", "parte", "part", "mov", "snapchat", "telegram", "signal",
}


@dataclass
class Suggestion:
    folder: tuple           # relative path of the folder, as it is now
    source: str             # "original": found inside a file | "content": from what it holds
    name: str               # the proposed name, ready to use
    kind: str = ""          # content: what most of it is (a key of KINDS, or "mixed")
    years: tuple = ()       # content: (first, last) year of the files, if they agree
    theme: str = ""         # content: a word most file names share
    evidence: int = 0       # original: how many paths point to it
    example: str = ""       # original: one of those paths
    files: int = 0


def _kind_of(it):
    return _KIND_OF.get(it.parts[-1].lower().rpartition(".")[2], "other")


def _kind(items):
    counts, sizes = collections.Counter(), collections.Counter()
    for it in items:
        name = it.parts[-1].lower()
        if name in SKIP_NAMES or name.startswith("._"):
            continue
        counts[_kind_of(it)] += 1
        sizes[_kind_of(it)] += it.size
    total, volume = sum(counts.values()), sum(sizes.values())
    if not total:
        return "mixed"
    kind, n = counts.most_common(1)[0]
    if kind != "other" and n * 10 >= total * 6:
        return kind
    # a photo beside its small note: what fills the folder says what it is
    big, b = sizes.most_common(1)[0]
    if big != "other" and b * 10 >= volume * 8 and counts[big] * 10 >= total * 4:
        return big
    # photos and videos together are what a phone or camera leaves
    if (counts["photos"] + counts["videos"]) * 10 >= total * 8 and counts["photos"]:
        return "photos"
    if (counts["documents"] + counts["spreadsheets"] + counts["presentations"]) * 10 >= total * 7:
        return "documents"
    return "mixed"


def _years(items, now=None):
    now = now or datetime.datetime.now()
    years = sorted(it.mtime.year for it in items
                   if it.mtime and 1990 <= it.mtime.year <= now.year + 1)
    if not years:
        return ()
    top, n = collections.Counter(years).most_common(1)[0]
    if n * 10 >= len(years) * 7:
        return (top, top)
    # leave out the odd file with a wrong clock at either end
    lo, hi = years[len(years) // 10], years[min(len(years) - 1, (len(years) * 9) // 10)]
    if hi - lo <= 4:
        return (lo, hi)
    return ()


def _theme(items):
    """A word at least half of the file names share ('boda', 'factura')."""
    names = [it.parts[-1].rpartition(".")[0] or it.parts[-1] for it in items
             if it.parts[-1].lower() not in SKIP_NAMES]
    if len(names) < 3:
        return ""
    counts = collections.Counter()
    for name in names:
        words = {w.lower() for w in re.findall(r"[^\W\d_]{4,}", name)}
        counts.update(words)
    for word, n in counts.most_common(5):
        if word not in STOP_WORDS and n * 2 >= len(names):
            return word
    return ""


def english_label(kind, years, theme):
    """Default wording; a window or command line supplies its own language."""
    words = {"photos": "Photos", "videos": "Videos", "music": "Music", "documents": "Documents",
             "spreadsheets": "Spreadsheets", "presentations": "Presentations",
             "programs": "Programs", "disk_images": "Disk images", "archives": "Archives",
             "code": "Code", "books": "Books", "fonts": "Fonts", "mixed": "Various"}
    return compose(words[kind], years, theme)


def compose(word, years, theme):
    name = word
    if theme:
        name += " " + theme
    if years:
        name += f" {years[0]}" if years[0] == years[1] else f" {years[0]}-{years[1]}"
    return name


# ---------------------------------------------------------------- suggest

def suggest(items, folders, label=english_label, budget=None):
    """items: every rescued file (clues can be anywhere). folders: paths of
    the folders that need a name. Returns a Suggestion for each."""
    budget = budget or {"files": MAX_FILES, "bytes": MAX_BYTES}
    folders = [_Folder(tuple(p)) for p in folders]
    by_path = {f.path: f for f in folders}
    for it in items:
        for n in (1, 2):
            f = by_path.get(it.parts[:n])
            if f and len(it.parts) > n:
                f.add(it)
    # names already in use beside them: a folder cannot be named like its neighbour
    taken = {it.parts[0].lower() for it in items if len(it.parts) > 1} - {f.path[0].lower() for f in folders}

    original = _original_names(folders, items, taken, budget)
    # two folders claiming the same original name: the one with more evidence keeps it
    owner = {}
    for path, (name, score, _) in original.items():
        low = name.lower()
        if low not in owner or score > original[owner[low]][1]:
            owner[low] = path

    out, used = [], set(taken)
    for f in folders:
        hit = original.get(f.path)
        if hit and owner[hit[0].lower()] == f.path:
            name, score, example = hit
            s = Suggestion(f.path, "original", sanitize(name), evidence=score, example=example,
                           files=len(f.items))
        else:
            kind = _kind(f.items)
            # the shared word is looked for among the files that make it what it is
            main = [it for it in f.items if _kind_of(it) == kind] if kind != "mixed" else f.items
            years, theme = _years(f.items), _theme(main or f.items)
            s = Suggestion(f.path, "content", sanitize(label(kind, years, theme)), kind=kind,
                           years=years, theme=theme, files=len(f.items))
        s.name = _unique(s.name, used)
        used.add(s.name.lower())
        out.append(s)
    return out


def _unique(name, used):
    if name.lower() not in used:
        return name
    n = 2
    while f"{name} ({n})".lower() in used:
        n += 1
    return f"{name} ({n})"


# -------------------------------------------------------- rename and undo

class RenameError(Exception):
    pass


def rename(dest, changes, log_path, report=None):
    """changes: [(relative folder path, new name)]. Renames inside dest,
    never on the drive being rescued. Every rename goes into the log first,
    so undo() can put things back. Returns the renames done."""
    done = []
    log = _read_log(log_path)
    for folder, new in changes:
        folder = os.path.join(*folder) if isinstance(folder, (tuple, list)) else folder
        new = sanitize(new).strip()
        if not new:
            continue
        src = os.path.join(dest, folder)
        target_rel = os.path.join(os.path.dirname(folder), new)
        target = os.path.join(dest, target_rel)
        if not os.path.isdir(src):
            raise RenameError(folder)
        if os.path.exists(target) and os.path.normcase(target) != os.path.normcase(src):
            raise RenameError(target_rel)
        log.append({"from": folder, "to": target_rel,
                    "when": datetime.datetime.now().isoformat(timespec="seconds")})
        _write_log(log_path, log)
        os.rename(src, target)
        done.append((folder, target_rel))
    if report and done:
        _rewrite_report(report, done)
    return done


def undo(dest, log_path, report=None):
    """Puts back every rename in the log, newest first. Returns how many."""
    log = _read_log(log_path)
    back = []
    while log:
        step = log[-1]
        src, target = os.path.join(dest, step["to"]), os.path.join(dest, step["from"])
        if os.path.isdir(src) and not os.path.exists(target):
            os.rename(src, target)
            back.append((step["to"], step["from"]))
        log.pop()
        _write_log(log_path, log)
    if not log and os.path.exists(log_path):
        os.remove(log_path)
    if report and back:
        _rewrite_report(report, back)
    return len(back)


def _read_log(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _write_log(path, log):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _rewrite_report(report, moves):
    """The report lists paths: they follow the folders that were renamed."""
    import csv
    try:
        with open(report, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except OSError:
        return
    for row in rows[1:]:
        if not row:
            continue
        for old, new in moves:
            if row[0] == old or row[0].startswith(old + os.sep):
                row[0] = new + row[0][len(old):]
    tmp = report + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    os.replace(tmp, report)
