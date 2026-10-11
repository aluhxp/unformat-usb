"""Original names of first-level folders, given away by leftovers of the root:
  - autorun.inf:  'icon=favicon\\usb.ico' says the unnamed folder holding
    usb.ico was called 'favicon';
  - Linux trash (.Trash-*/info): 'Path=Photos/2020/a.jpg' says the one holding
    '2020' was called 'Photos'."""

import re
import urllib.parse

from .orphans import text_part
from .util import sanitize


def name_clues(disk, g, orphans, contents, unnamed_tops):
    """unnamed_tops: {folder cluster: current placeholder path}.
    Returns {placeholder path: original name}."""
    pairs = []   # (first-level folder, something that was inside it)
    for o in orphans:
        if o.ext not in ("autorun.inf", "trashinfo"):
            continue
        text = text_part(disk.read(g.coff(o.cluster), min(8192, g.cs))).decode("utf-8", "replace")
        if o.ext == "autorun.inf":
            values = [v.split(",")[0].strip('"') for _, v in
                      re.findall(r"(?im)^\s*(icon|open|shellexecute)\s*=\s*(.+?)\s*$", text)]
        else:
            values = [urllib.parse.unquote(v) for v in re.findall(r"(?m)^Path=(.+?)\s*$", text)]
        for value in values:
            parts = [x for x in re.split(r"[\\/]", value) if x and x != "."]
            if len(parts) >= 2 and not re.match(r"^[A-Za-z]:$", parts[0]):
                pairs.append((parts[0], parts[1]))
    found = {}
    for folder, child in pairs:
        match = [c for c in unnamed_tops
                 if any(en.name.lower() == child.lower() for en in contents[c])]
        if len(match) == 1 and unnamed_tops[match[0]] not in found and sanitize(folder) not in found.values():
            found[unnamed_tops[match[0]]] = sanitize(folder)
    return found
