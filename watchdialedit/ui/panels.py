import json
from PyQt6.QtCore import Qt, QSize, QTime, QDate
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                             QPushButton, QSpinBox, QFormLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QTimeEdit,
                             QDateEdit, QDoubleSpinBox, QGroupBox, QHeaderView, QLineEdit, QMenu,
                             QComboBox)
from .model import ProjectModel
from .qt_utils import pil_to_pixmap
from .asset_picker_dialog import AssetPickerDialog
from ..core.renderer import default_hand_anchor


class LayersPanel(QWidget):
    """Layers == iwf.json item[]. Top of the list = last item = drawn on top."""

    def __init__(self, model: ProjectModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Up", lambda: self._move(+1)), ("Down", lambda: self._move(-1)),
                         ("Dup", model.duplicate_selected), ("Del", model.delete_selected)):
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        lay.addLayout(row)
        self._busy = False
        self.list.itemSelectionChanged.connect(self._on_sel)
        model.changed.connect(self.rebuild)
        model.selectionChanged.connect(self._sync_sel)
        self.rebuild()

    def rebuild(self):
        self._busy = True
        self.list.clear()
        items = self.model.project.iwf.items()
        for i in range(len(items) - 1, -1, -1):
            it = items[i]
            li = QListWidgetItem("%d  %s" % (i, it.label()))
            li.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(li)
        self._busy = False
        self._sync_sel()

    def _sync_sel(self):
        self._busy = True
        for r in range(self.list.count()):
            li = self.list.item(r)
            li.setSelected(li.data(Qt.ItemDataRole.UserRole) in self.model.selection)
        self._busy = False

    def _on_sel(self):
        if self._busy:
            return
        self.model.select([li.data(Qt.ItemDataRole.UserRole) for li in self.list.selectedItems()])

    def _move(self, d):
        if len(self.model.selection) == 1:
            self.model.move_layer(self.model.selection[0], d)


def _parse_value(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


class InspectorPanel(QWidget):
    """Edits the raw item dict. Every field of the real IWF item (including ones this
    app does not know) is listed and editable; values keep their JSON type."""

    def __init__(self, model: ProjectModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("No selection")
        lay.addWidget(self.title)
        form = QFormLayout()
        self.spins = {}
        for k in ("x", "y", "w", "h"):
            s = QSpinBox(); s.setRange(-4096, 4096)
            s.editingFinished.connect(self._geom_edited)
            self.spins[k] = s
            form.addRow(k.upper(), s)
        lay.addLayout(form)
        self.hands_box = QGroupBox("Watch hands")
        hands_lay = QVBoxLayout(self.hands_box)
        self.hand_widgets = {}
        for short, label in (("hour", "Hour"), ("minute", "Minute"), ("second", "Second")):
            row = QHBoxLayout()
            row.addWidget(QLabel(label + ":"))
            path_label = QLabel("(none)")
            path_label.setStyleSheet("color: gray;")
            row.addWidget(path_label, 1)
            btn_choose = QPushButton("Choose image...")
            btn_choose.clicked.connect(lambda _=False, s=short: self._choose_hand(s))
            btn_clear = QPushButton("Clear")
            btn_clear.clicked.connect(lambda _=False, s=short: self._clear_hand(s))
            row.addWidget(btn_choose)
            row.addWidget(btn_clear)
            hands_lay.addLayout(row)
            self.hand_widgets[short] = path_label
        lay.addWidget(self.hands_box)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["field", "value (JSON)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemChanged.connect(self._cell_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        lay.addWidget(self.table)
        add_row = QHBoxLayout()
        self.new_key = QLineEdit(); self.new_key.setPlaceholderText("field")
        self.new_val = QLineEdit(); self.new_val.setPlaceholderText("value")
        self.btn_browse_new = QPushButton("Browse...")
        self.btn_browse_new.clicked.connect(self._browse_for_new)
        self.field_type_combo = QComboBox()
        self.field_type_combo.addItems(["string", "number", "boolean"])
        self.field_type_combo.currentIndexChanged.connect(lambda _: self.new_val.clear())
        self.btn_add_field = QPushButton("Add field")
        self.btn_add_field.clicked.connect(self._add_field)
        add_row.addWidget(self.new_key)
        add_row.addWidget(self.new_val, 1)
        add_row.addWidget(self.btn_browse_new)
        add_row.addWidget(self.field_type_combo)
        add_row.addWidget(self.btn_add_field)
        lay.addLayout(add_row)
        self._busy = False
        model.changed.connect(self.reload)
        model.selectionChanged.connect(self.reload)
        self.reload()

    def _single(self):
        return self.model.selection[0] if len(self.model.selection) == 1 else None

    def reload(self):
        self._busy = True
        idx = self._single()
        multi = len(self.model.selection) > 1
        for s in self.spins.values():
            s.setEnabled(idx is not None or multi)
        for w in (self.new_key, self.new_val, self.btn_browse_new, self.btn_add_field):
            w.setEnabled(idx is not None)
        self.table.setRowCount(0)
        self.hands_box.setVisible(False)
        if idx is None or idx >= len(self.model.project.iwf):
            self.title.setText("%d selected" % len(self.model.selection) if multi else "No selection")
            self._busy = False
            return
        it = self.model.project.iwf.item_at(idx)
        self.title.setText("Item %d  -  %s" % (idx, it.label()))
        if it.widget == "watch":
            self.hands_box.setVisible(True)
            for short, path_label in self.hand_widgets.items():
                v = it.get(short)
                path_label.setText(v if v else "(none)")
        for k in it.GEOM:
            self.spins[k].setValue(getattr(it, k))
        for r, (k, v) in enumerate(it.data.items()):
            self.table.insertRow(r)
            ki = QTableWidgetItem(k); ki.setFlags(ki.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, ki)
            self.table.setItem(r, 1, QTableWidgetItem(json.dumps(v, ensure_ascii=False)))
        self._busy = False

    def _geom_edited(self):
        if self._busy or not self.model.selection:
            return
        vals = {k: s.value() for k, s in self.spins.items()}
        if len(self.model.selection) == 1:
            self.model.set_geometry(self.model.selection, **vals)
        else:                       # multi: only apply x/y as absolute for all (explicit user act)
            self.model.set_geometry(self.model.selection, x=vals["x"], y=vals["y"])

    def _cell_changed(self, cell):
        if self._busy or cell.column() != 1:
            return
        idx = self._single()
        if idx is None:
            return
        key = self.table.item(cell.row(), 0).text()
        self.model.set_field(idx, key, _parse_value(cell.text()))

    def _add_field(self):
        idx = self._single()
        if idx is None:
            return
        key = self.new_key.text().strip()
        if not key:
            return
        # The type combo overrides JSON auto-detection so e.g. "30" can be forced to
        # the string "30" instead of the number 30, or vice versa.
        type_index = self.field_type_combo.currentIndex()
        if type_index == 0:        # string
            value = self.new_val.text()
        elif type_index == 1:      # number
            try:
                value = float(self.new_val.text())
            except ValueError:
                value = 0.0
        elif type_index == 2:      # boolean
            value = self.new_val.text().strip().lower() in ("true", "1", "yes")
        else:
            value = _parse_value(self.new_val.text())
        self.model.set_field(idx, key, value)
        self.new_key.clear()
        self.new_val.clear()

    # The hand *image* field keeps its full name (hour/minute/second), but its
    # centerx/centery/anchorx/anchory sub-fields use an abbreviated prefix for minute
    # and second - "min"/"sec" - while hour stays "hour". Confirmed against a real
    # exported watch item; do not "normalize" this to match the image field name.
    _HAND_PREFIX = {"hour": "hour", "minute": "min", "second": "sec"}

    def _choose_hand(self, short):
        idx = self._single()
        if idx is None:
            return
        dlg = AssetPickerDialog(self.model.project.assets, self)
        if dlg.exec() != dlg.DialogCode.Accepted or dlg.result_path() is None:
            return
        path = dlg.result_path()
        it = self.model.project.iwf.item_at(idx)
        prefix = self._HAND_PREFIX[short]
        values = {short: path}
        img = self.model.project.assets.image(path)
        if img is not None:
            # Pivot defaults match what the renderer already falls back to when these
            # fields are absent (bottom-centre of the hand image; the device's confirmed
            # anchor point, or the item's box centre if the device's isn't known) -
            # written out explicitly here so they show up as editable right away.
            ax_def, ay_def = default_hand_anchor(self.model.project, it)
            values[prefix + "centerx"] = img.width // 2
            values[prefix + "centery"] = img.height
            values[prefix + "anchorx"] = ax_def
            values[prefix + "anchory"] = ay_def
        self.model.set_fields(idx, values, text="Set %s hand" % short)

    def _clear_hand(self, short):
        idx = self._single()
        if idx is None:
            return
        prefix = self._HAND_PREFIX[short]
        keys = [short, prefix + "centerx", prefix + "centery", prefix + "anchorx", prefix + "anchory"]
        self.model.remove_fields(idx, keys)

    def _browse_for_new(self):
        dlg = AssetPickerDialog(self.model.project.assets, self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_path() is not None:
            self.new_val.setText(dlg.result_path())

    def _table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        idx = self._single()
        if row < 0 or idx is None:
            return
        key = self.table.item(row, 0).text()
        menu = QMenu(self)
        act_browse = menu.addAction("Browse for asset...")
        act_remove = menu.addAction("Remove field")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_browse:
            dlg = AssetPickerDialog(self.model.project.assets, self)
            if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_path() is not None:
                self.model.set_field(idx, key, dlg.result_path())
        elif chosen is act_remove:
            self.model.remove_field(idx, key)


class AssetBrowser(QTreeWidget):
    """Read-only view of the project's real asset files (root images + glyph groups)."""

    def __init__(self, model: ProjectModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.setHeaderLabels(["asset"])
        self.setIconSize(QSize(32, 32))
        model.changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self):
        self.clear()
        a = self.model.project.assets
        root = QTreeWidgetItem(["(root)"]); self.addTopLevelItem(root)
        for f in a.root_images():
            it = QTreeWidgetItem([f])
            im = a.image(f)
            if im is not None:
                it.setIcon(0, QIcon(pil_to_pixmap(im.copy().resize(_fit(im.size, 32)))))
            root.addChild(it)
        for d in a.group_dirs():
            g = QTreeWidgetItem([d + "/"]); self.addTopLevelItem(g)
            for f in a.group_files(d):
                it = QTreeWidgetItem([f]); g.addChild(it)
                im = a.image(d + "/" + f)
                if im is not None:
                    it.setIcon(0, QIcon(pil_to_pixmap(im.copy().resize(_fit(im.size, 32)))))
        root.setExpanded(True)


def _fit(size, box):
    w, h = size
    s = min(box / max(w, 1), box / max(h, 1), 1.0)
    return max(1, int(w * s)), max(1, int(h * s))


class PreviewPanel(QWidget):
    """Editor-only preview inputs (not stored in iwf.json)."""

    def __init__(self, model: ProjectModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QFormLayout(self)
        p = model.preview
        self.time = QTimeEdit(QTime(p.hour, p.minute, p.second)); self.time.setDisplayFormat("HH:mm:ss")
        self.date = QDateEdit(QDate(p.year, p.month, p.day))
        self.frame = QSpinBox(); self.frame.setRange(0, 999); self.frame.setValue(p.anima_frame)
        lay.addRow("Time", self.time)
        lay.addRow("Date", self.date)
        lay.addRow("Anim frame", self.frame)
        self.vals = {}
        for k, v in p.values.items():
            s = QDoubleSpinBox(); s.setRange(0, 999999); s.setDecimals(2 if k == "distance" else 0)
            s.setValue(v); s.valueChanged.connect(self._push); self.vals[k] = s
            lay.addRow(k, s)
        self.time.timeChanged.connect(self._push)
        self.date.dateChanged.connect(self._push)
        self.frame.valueChanged.connect(self._push)

    def _push(self, *_):
        import copy
        p = copy.deepcopy(self.model.preview)
        t, d = self.time.time(), self.date.date()
        p.hour, p.minute, p.second = t.hour(), t.minute(), t.second()
        p.year, p.month, p.day = d.year(), d.month(), d.day()
        p.anima_frame = self.frame.value()
        for k, s in self.vals.items():
            p.values[k] = s.value()
        self.model.set_preview(p)