"""The folder tree shown while scanning, as a flat list of the visible rows.

Folders arrive in any order: one found before its parent waits in the
"locating" group and moves to its place when the parent shows up."""

import os

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

PENDING = -1    # id of the "still locating" group


class Node:
    __slots__ = ("id", "name", "parent", "children", "files", "size", "checked",
                 "expanded", "lost_name", "total_files", "total_size")

    def __init__(self, node_id, name=None):
        self.id, self.name = node_id, name
        self.parent, self.children = None, []
        self.files = self.size = 0              # its own files
        self.total_files = self.total_size = 0  # ...plus everything below it
        self.checked, self.expanded, self.lost_name = True, False, False

    @property
    def depth(self):
        d, n = -1, self
        while n.parent is not None:
            d, n = d + 1, n.parent
        return d


class FolderTreeModel(QAbstractListModel):
    ROLES = {Qt.UserRole + i: name.encode() for i, name in enumerate(
        ("nodeId", "name", "depth", "totalFiles", "totalSize", "checked", "expanded",
         "hasChildren", "lostName", "isPending", "isGroup"))}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear()

    def clear(self):
        self.beginResetModel()
        self.root = Node(None)
        self.pending = Node(PENDING)
        self.pending.expanded = True
        self.nodes = {}
        self.rows = []
        self.endResetModel()

    # ----------------------------------------------------------- Qt model

    def roleNames(self):
        return self.ROLES

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not 0 <= index.row() < len(self.rows):
            return None
        n = self.rows[index.row()]
        key = self.ROLES.get(role, b"").decode()
        if key == "nodeId":
            return n.id
        if key == "name":
            return n.name or ""
        if key == "depth":
            return n.depth
        if key == "totalFiles":
            return n.total_files
        if key == "totalSize":
            return n.total_size
        if key == "checked":
            return n.checked
        if key == "expanded":
            return n.expanded
        if key == "hasChildren":
            return bool(n.children)
        if key == "lostName":
            return n.lost_name
        if key == "isPending":
            return self._under_pending(n)
        if key == "isGroup":
            return n is self.pending
        return None

    def _under_pending(self, n):
        while n.parent is not None:
            if n.parent is self.pending:
                return True
            n = n.parent
        return False

    # ------------------------------------------------------------- content

    def _attach(self, node, parent):
        if node.parent is not None:
            node.parent.children.remove(node)
        node.parent = parent
        parent.children.append(node)

    def folder_found(self, cluster, parent, name, files, size):
        node = self.nodes.get(cluster)
        if node is None:
            node = self.nodes[cluster] = Node(cluster, name)
        node.files, node.size = files, size
        if name:
            node.name = name
        self._attach(node, self.nodes.get(parent, self.pending) if parent else self.pending)

    def folder_placed(self, cluster, parent, name, unnamed_label):
        node = self.nodes.get(cluster)
        if node is None:
            return
        if parent == 0:
            node.name = name or unnamed_label.format(cluster)
            node.lost_name = not name
            self._attach(node, self.root)
        elif parent in self.nodes:
            node.name = name or node.name
            self._attach(node, self.nodes[parent])

    def rebuild(self, result):
        """Final, authoritative shape once the scan is over."""
        checked = {c: n.checked for c, n in self.nodes.items()}
        expanded = {c for c, n in self.nodes.items() if n.expanded}
        unnamed = result.names.unnamed_folder.split("{")[0]
        self.beginResetModel()
        self.root, self.pending, self.nodes = Node(None), Node(PENDING), {}
        for c, ents in result.contents.items():
            node = self.nodes[c] = Node(c, os.path.basename(result.paths[c]))
            files = [en for en in ents if not en.is_dir]
            node.files, node.size = len(files), sum(en.size for en in files)
            node.checked, node.expanded = checked.get(c, True), c in expanded
        for c, node in self.nodes.items():
            p = result.parent_of.get(c)
            inside = p in self.nodes and p != c and \
                result.paths[c].startswith(result.paths[p] + os.sep)
            if inside:
                self._attach(node, self.nodes[p])
            else:
                node.name = result.paths[c]
                node.lost_name = node.name.startswith(unnamed)
                self._attach(node, self.root)
        self.rows = self._visible()
        self.endResetModel()

    # ------------------------------------------------------------ visible

    def _totals(self):
        """Add up each folder with everything inside it, children first."""
        order, stack = [], [self.root, self.pending]
        while stack:
            n = stack.pop()
            order.append(n)
            stack += n.children
        for n in reversed(order):
            n.total_files = n.files + sum(c.total_files for c in n.children)
            n.total_size = n.size + sum(c.total_size for c in n.children)

    def _visible(self):
        self._totals()
        out = []

        def walk(node):
            for child in node.children:
                out.append(child)
                if child.expanded:
                    walk(child)

        walk(self.root)
        if self.pending.children:
            out.append(self.pending)
            walk(self.pending)
        return out

    def refresh(self):
        """Bring the visible rows in line with the tree, row by row when the
        change is only rows coming and going."""
        new = self._visible()
        keep = set(new)
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i] not in keep:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self.rows[i]
                self.endRemoveRows()
        position = {n: i for i, n in enumerate(new)}
        if [position[n] for n in self.rows] != sorted(position[n] for n in self.rows):
            self.beginResetModel()          # rows changed order: start over
            self.rows = new
            self.endResetModel()
            return
        i = 0
        while i < len(new):
            if i < len(self.rows) and self.rows[i] is new[i]:
                i += 1
                continue
            j = i
            while j < len(new) and not (i < len(self.rows) and self.rows[i] is new[j]):
                j += 1
            self.beginInsertRows(QModelIndex(), i, j - 1)
            self.rows[i:i] = new[i:j]
            self.endInsertRows()
            i = j
        if self.rows:
            self.dataChanged.emit(self.index(0), self.index(len(self.rows) - 1))

    # ---------------------------------------------------------- interaction

    def toggle_expanded(self, row):
        if 0 <= row < len(self.rows) and self.rows[row].children:
            self.rows[row].expanded = not self.rows[row].expanded
            self.refresh()

    def set_checked(self, row, value):
        if not 0 <= row < len(self.rows):
            return
        stack = [self.rows[row]]
        while stack:
            n = stack.pop()
            n.checked = value
            stack += n.children
        self.dataChanged.emit(self.index(0), self.index(len(self.rows) - 1))

    def selected(self):
        """(folder clusters, file count, bytes) of everything ticked."""
        picked = [n for n in self.nodes.values() if n.checked]
        return ({n.id for n in picked}, sum(n.files for n in picked), sum(n.size for n in picked))
