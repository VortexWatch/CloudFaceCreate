"""ProjectModel: the single mutation gateway between the UI and the IWF document.

Canvas / panels never own data. They call model methods, which edit
`project.iwf.raw_items` (the real iwf.json `item[]`) through undoable commands.
Editor-only state (grid, snap, zoom, selection, preview time) lives here and is never
written to iwf.json.
"""
import copy
from typing import Callable, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QUndoCommand, QUndoStack
from ..core.project import Project
from ..core.preview_state import PreviewState
from ..core.renderer import render_face, RenderResult


class SnapshotCommand(QUndoCommand):
    """Whole item[] before/after. The list is small (tens of dicts) so this is simple
    and cannot desynchronise; merge ids collapse rapid inspector edits."""

    def __init__(self, model: "ProjectModel", before, after, text, merge_id=-1):
        super().__init__(text)
        self.model, self.before, self.after, self._merge = model, before, after, merge_id
        self._first = True

    def id(self):
        return self._merge

    def mergeWith(self, other):
        if self._merge != -1 and other.id() == self._merge:
            self.after = other.after
            return True
        return False

    def redo(self):
        if self._first:            # state already applied when the command was created
            self._first = False
            self.model._notify()
            return
        self.model._set_items(self.after)

    def undo(self):
        self.model._set_items(self.before)


class ProjectModel(QObject):
    changed = pyqtSignal()            # document / render affecting change
    selectionChanged = pyqtSignal()
    editorStateChanged = pyqtSignal()  # grid/snap/zoom/preview state (never affects export)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.undo = QUndoStack(self)
        self.selection: List[int] = []
        self.preview = PreviewState()
        self.grid_enabled = True
        self.grid_spacing = 10
        self.snap_enabled = True
        self.show_rulers = True
        self.show_overlays = True
        self._render: Optional[RenderResult] = None

    # ------------------------------------------------------------ rendering
    def render(self) -> RenderResult:
        """Export-safe watch-face render (no overlays). Cached until the model changes."""
        if self._render is None:
            self._render = render_face(self.project, self.preview)
        return self._render

    def _notify(self):
        self._render = None
        self.project.dirty = True
        self.selection = [i for i in self.selection if i < len(self.project.iwf)]
        self.changed.emit()

    def _set_items(self, items):
        self.project.iwf.root["item"][:] = copy.deepcopy(items)
        self._notify()
        self.selectionChanged.emit()

    def set_preview(self, state: PreviewState):
        self.preview = state
        self._render = None
        self.editorStateChanged.emit()
        self.changed.emit()

    # ------------------------------------------------------------ editing
    def snapshot(self):
        return copy.deepcopy(self.project.iwf.raw_items)

    def edit(self, text: str, mutate: Callable[[], None], merge_id: int = -1):
        """Run `mutate()` (which edits raw item dicts), then record one undo step."""
        before = self.snapshot()
        mutate()
        self.commit(before, text, merge_id)

    def commit(self, before, text: str, merge_id: int = -1):
        after = self.snapshot()
        if after == before:
            return
        self.undo.push(SnapshotCommand(self, before, after, text, merge_id))
        
    def set_fields(self, index: int, values: dict, text: str = "Edit fields"):
        def m():
            self.project.iwf.raw_items[index].update(values)
        self.edit(text, m)

    def remove_fields(self, index: int, keys) -> None:
        def m():
            d = self.project.iwf.raw_items[index]
            for k in keys:
                d.pop(k, None)
        self.edit("Remove fields", m)

    def set_field(self, index: int, key: str, value):
        def m():
            self.project.iwf.raw_items[index][key] = value
        self.edit("Edit %s" % key, m, merge_id=hash((index, key)) & 0x7FFFFFF)

    def remove_field(self, index: int, key: str):
        self.edit("Remove %s" % key, lambda: self.project.iwf.raw_items[index].pop(key, None))

    def set_geometry(self, indices, x=None, y=None, w=None, h=None):
        def m():
            for i in indices:
                self.project.iwf.item_at(i).set_geometry(x, y, w, h)
        self.edit("Move/Resize", m)

    def add_item(self, data: dict):
        def m():
            self.project.iwf.raw_items.append(data)
        self.edit("Add widget", m)
        self.select([len(self.project.iwf) - 1])

    def delete_selected(self):
        idx = sorted(self.selection, reverse=True)
        if not idx:
            return

        def m():
            for i in idx:
                self.project.iwf.remove_item(i)
        self.edit("Delete", m)
        self.select([])

    def duplicate_selected(self):
        idx = sorted(self.selection)
        if not idx:
            return
        n0 = len(self.project.iwf)

        def m():
            for i in idx:
                d = copy.deepcopy(self.project.iwf.raw_items[i])
                d["x"] = int(d.get("x", 0)) + 10
                d["y"] = int(d.get("y", 0)) + 10
                self.project.iwf.raw_items.append(d)
        self.edit("Duplicate", m)
        self.select(list(range(n0, n0 + len(idx))))

    def move_layer(self, index: int, delta: int):
        j = index + delta
        if j < 0 or j >= len(self.project.iwf):
            return
        self.edit("Reorder layer", lambda: self.project.iwf.move_item(index, j))
        self.select([j])

    def set_doc_field(self, key: str, value):
        """Document-level iwf.json fields (deviceId, name, ...)."""
        before = self.snapshot()
        old = self.project.iwf.root.get(key)
        if old == value:
            return
        self.project.iwf.root[key] = value
        self.undo.push(_DocFieldCommand(self, key, old, value))

    # ------------------------------------------------------------ selection
    def select(self, indices):
        self.selection = sorted(set(indices))
        self.selectionChanged.emit()

    def select_all(self):
        self.select(list(range(len(self.project.iwf))))


class _DocFieldCommand(QUndoCommand):
    def __init__(self, model, key, old, new):
        super().__init__("Set %s" % key)
        self.model, self.key, self.old, self.new = model, key, old, new
        self._first = True

    def redo(self):
        self.model.project.iwf.root[self.key] = self.new
        self.model._notify()

    def undo(self):
        if self.old is None:
            self.model.project.iwf.root.pop(self.key, None)
        else:
            self.model.project.iwf.root[self.key] = self.old
        self.model._notify()
