"""Turn parent links into relative paths."""

import os

from .util import sanitize


def build_paths(parent_of, contents, root_ents, root_cl, names):
    known = {}
    for en in root_ents:
        if en.is_dir and en.cluster in contents:
            known.setdefault(en.cluster, en.name)
    for par, ents in contents.items():
        for en in ents:
            if en.is_dir and en.cluster in contents and parent_of.get(en.cluster) == par:
                known.setdefault(en.cluster, en.name)
    paths = {}

    def path_of(c, depth=0):
        if c in paths:
            return paths[c]
        par = parent_of.get(c, 0)
        name = sanitize(known.get(c, names.unnamed_folder.format(c)))
        if par in (0, root_cl, c) or depth > 100:
            p = name
        elif par not in contents:
            p = os.path.join(names.lost_parent, name)
        else:
            p = os.path.join(path_of(par, depth + 1), name)
        paths[c] = p
        return p

    for c in contents:
        path_of(c)
    return paths, known
