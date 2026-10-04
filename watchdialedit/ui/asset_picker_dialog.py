"""Modal picker for assigning an asset-reference field (bg, pointer, icon_bg, font,
animaicon, sunswitch, hour/minute/second, ...) to the string value the item schema
expects. Some fields want a root image filename or a 'group/file' path (bg, pointer,
icon_bg, the watch-hand fields); others want a bare glyph-group name (font, animaicon,
sunswitch) - so both a group node and the files inside it are selectable here."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
                             QDialogButtonBox, QLabel)
from ..core.assets import AssetManager
from .qt_utils import pil_to_pixmap


class AssetPickerDialog(QDialog):
    """Pick a root image, a whole glyph group, or a file inside a glyph group.
    result_path() returns the string to store in the field, or None on cancel."""

    def __init__(self, assets: AssetManager, parent=None):
        super().__init__(parent)
        self.assets = assets
        self.setWindowTitle("Choose asset")
        self.resize(360, 420)
        self._result = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Pick a root image, a group (for group-name fields like 'font' /\n"
            "'animaicon' / 'sunswitch'), or a file inside a group:"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(32, 32))
        lay.addWidget(self.tree)
        self._build_tree()
        self.tree.itemDoubleClicked.connect(lambda _=None: self._accept())
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _build_tree(self):
        root = QTreeWidgetItem(["(root)"])
        root.setData(0, Qt.ItemDataRole.UserRole, None)      # not selectable as a value
        self.tree.addTopLevelItem(root)
        for f in self.assets.root_images():
            it = QTreeWidgetItem([f])
            it.setData(0, Qt.ItemDataRole.UserRole, f)
            im = self.assets.image(f)
            if im is not None:
                it.setIcon(0, QIcon(pil_to_pixmap(im.copy().resize(_fit(im.size, 32)))))
            root.addChild(it)
        for d in self.assets.group_dirs():
            g = QTreeWidgetItem([d + "/"])
            g.setData(0, Qt.ItemDataRole.UserRole, d)        # the group node = bare group name
            self.tree.addTopLevelItem(g)
            for f in self.assets.group_files(d):
                it = QTreeWidgetItem([f])
                it.setData(0, Qt.ItemDataRole.UserRole, d + "/" + f)
                im = self.assets.image(d + "/" + f)
                if im is not None:
                    it.setIcon(0, QIcon(pil_to_pixmap(im.copy().resize(_fit(im.size, 32)))))
                g.addChild(it)
        root.setExpanded(True)

    def _accept(self):
        items = self.tree.selectedItems()
        if not items:
            return
        path = items[0].data(0, Qt.ItemDataRole.UserRole)
        if path is None:          # "(root)" header itself - not a real choice
            return
        self._result = path
        self.accept()

    def result_path(self):
        return self._result


def _fit(size, box):
    w, h = size
    s = min(box / max(w, 1), box / max(h, 1), 1.0)
    return max(1, int(w * s)), max(1, int(h * s))