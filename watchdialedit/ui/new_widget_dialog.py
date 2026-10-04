"""New Widget dialog: Watch / Custom / Ring / Progressbar tabs, each listing the real
widget types for that category (core.widget_catalog.WIDGET_CATEGORIES). Picking an entry
creates the exact item[] schema established from app.js - see docs/FINDINGS.md."""
from typing import Optional, Tuple
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QListWidget,
                             QListWidgetItem, QDialogButtonBox, QComboBox, QLabel, QWidget)
from PyQt6.QtCore import Qt
from ..core.widget_catalog import WIDGET_CATEGORIES


class NewWidgetDialog(QDialog):
    def __init__(self, font_groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Widget")
        self.resize(420, 360)
        self._result: Optional[Tuple[str, str, bool]] = None
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.lists = {}
        for category, entries in WIDGET_CATEGORIES.items():
            lw = QListWidget()
            for key, label, needs_font, _factory in entries:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, (key, needs_font))
                lw.addItem(item)
            lw.itemDoubleClicked.connect(lambda _=None: self._accept())
            self.tabs.addTab(lw, category)
            self.lists[category] = lw
        row = QHBoxLayout()
        row.addWidget(QLabel("Glyph group (font.json):"))
        self.font_combo = QComboBox()
        self.font_combo.addItem("(none)")
        self.font_combo.addItems(font_groups)
        row.addWidget(self.font_combo, 1)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _current(self):
        lw = self.tabs.currentWidget()
        items = lw.selectedItems()
        if not items:
            return None
        return self.tabs.tabText(self.tabs.currentIndex()), items[0]

    def _accept(self):
        cur = self._current()
        if cur is None:
            return
        _, item = cur
        key, needs_font = item.data(Qt.ItemDataRole.UserRole)
        font = "" if self.font_combo.currentIndex() == 0 else self.font_combo.currentText()
        self._result = (key, font, needs_font)
        self.accept()

    def result_choice(self) -> Optional[Tuple[str, str, bool]]:
        """(widget_key, chosen_font_group_or_'', needs_font_group)."""
        return self._result