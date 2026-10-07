import copy
import os
from collections import OrderedDict
from PyQt6.QtCore import Qt, QTimer, QRectF, QRect
from PyQt6.QtGui import QAction, QKeySequence, QActionGroup, QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import (QMainWindow, QFileDialog, QMessageBox, QDockWidget, QWidget, QGridLayout,
                             QToolBar, QComboBox, QLabel, QInputDialog, QSpinBox, QTabWidget, QApplication)
from ..core.project import Project
from ..core import iwf_packer, pixel_codec as pc
from ..core.devices import VERIFIED_DEVICES
from ..core.widget_catalog import WIDGET_CATEGORIES
from .model import ProjectModel
from .canvas import FaceView, Ruler
from .panels import LayersPanel, InspectorPanel, AssetBrowser, PreviewPanel
from .new_widget_dialog import NewWidgetDialog

_FACTORY_BY_KEY = {key: factory for entries in WIDGET_CATEGORIES.values()
                   for key, _label, _needs_font, factory in entries}


class MainWindow(QMainWindow):
    def __init__(self, project: Project = None):
        super().__init__()
        self.setWindowTitle("CloudFaceCreate")
        self.resize(1400, 900)
        self.model = None
        self._build_actions()
        self._build_menus()
        self.statusBar().showMessage("Open an IWF design folder (File > Open) to begin")
        if project:
            self.set_project(project)

    # ------------------------------------------------------------------ project
    def set_project(self, project: Project):
        self.model = ProjectModel(project, self)
        m = self.model
        self.view = FaceView(m)
        central = QWidget()
        g = QGridLayout(central)
        g.setContentsMargins(0, 0, 0, 0); g.setSpacing(0)
        g.addWidget(QLabel(""), 0, 0)
        self.hr, self.vr = Ruler(self.view, True), Ruler(self.view, False)
        g.addWidget(self.hr, 0, 1); g.addWidget(self.vr, 1, 0); g.addWidget(self.view, 1, 1)
        self.setCentralWidget(central)
        for dock in self.findChildren(QDockWidget):
            dock.deleteLater()
        self._dock("Layers", LayersPanel(m), Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("Inspector", InspectorPanel(m), Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("Assets", AssetBrowser(m), Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock("Preview", PreviewPanel(m), Qt.DockWidgetArea.LeftDockWidgetArea)
        self._build_toolbar()
        m.changed.connect(self._update_title)
        m.undo.cleanChanged.connect(lambda _: self._update_title())
        self._update_title()
        self._rewire_undo()
        QTimer.singleShot(0, self.view.zoom_fit)      # viewport has no real size yet

    def _dock(self, title, widget, area):
        d = QDockWidget(title, self); d.setWidget(widget); self.addDockWidget(area, d)

    def _update_title(self):
        if not self.model:
            return
        p = self.model.project
        self.setWindowTitle("CloudFaceCreate - %s%s  [%s]" % (
            p.iwf.get("name", ""), " *" if p.dirty else "", p.root))
        unsupported = self.model.render().unsupported
        self.statusBar().showMessage(
            "Widgets not rendered (behaviour not established): %s" % ", ".join(unsupported) if unsupported
            else "%d widgets" % len(p.iwf))

    def _rewire_undo(self):
        self.model.undo.canUndoChanged.connect(self.act_undo.setEnabled)
        self.model.undo.canRedoChanged.connect(self.act_redo.setEnabled)
        self.act_undo.setEnabled(self.model.undo.canUndo())
        self.act_redo.setEnabled(self.model.undo.canRedo())

    # ------------------------------------------------------------------ actions
    def _act(self, text, slot, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        if checkable:
            a.setCheckable(True); a.setChecked(checked)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        S = QKeySequence.StandardKey
        self.act_open = self._act("&Open Watch Face...", self.open_dialog, S.Open)
        self.act_save = self._act("&Save", self.save, S.Save)
        self.act_save_as = self._act("Save &As...", self.save_as, S.SaveAs)
        self.act_export_iwf = self._act("Export &Watch Face...", self.export_iwf, "Ctrl+E")
        self.act_export_png = self._act("Export Preview &PNG...", self.export_png)
        self.act_quit = self._act("&Quit", self.close, S.Quit)
        # dispatch dynamically to the *current* model so re-opening a project never
        # leaves actions wired to a stale undo stack
        self.act_undo = self._act("&Undo", lambda: self.model and self.model.undo.undo(), S.Undo)
        self.act_redo = self._act("&Redo", lambda: self.model and self.model.undo.redo(), S.Redo)
        self.act_undo.setEnabled(False); self.act_redo.setEnabled(False)
        self.act_dup = self._act("&Duplicate", lambda: self.model.duplicate_selected(), "Ctrl+D")
        self.act_del = self._act("De&lete", lambda: self.model.delete_selected(), S.Delete)
        self.act_all = self._act("Select &All", lambda: self.model.select_all(), S.SelectAll)
        self.act_add = self._act("&Add Widget...", self.add_widget, "Ctrl+N")
        self.act_zin = self._act("Zoom &In", lambda: self.view.set_zoom(self.view.zoom * 1.25), S.ZoomIn)
        self.act_zout = self._act("Zoom &Out", lambda: self.view.set_zoom(self.view.zoom / 1.25), S.ZoomOut)
        self.act_fit = self._act("&Fit", lambda: self.view.zoom_fit(), "Ctrl+0")
        self.act_100 = self._act("&100%", lambda: self.view.set_zoom(1.0), "Ctrl+1")
        self.act_grid = self._act("Show &Grid", lambda c: self._flag("grid_enabled", c), "Ctrl+'", True, True)
        self.act_snap = self._act("&Snap", lambda c: self._flag("snap_enabled", c), None, True, True)
        self.act_rulers = self._act("&Rulers", self._toggle_rulers, None, True, True)
        self.act_overlay = self._act("Editor &Overlays", lambda c: self._flag("show_overlays", c), None, True, True)

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        for a in (self.act_open, self.act_save, self.act_save_as, None, self.act_export_iwf,
                  self.act_export_png, None, self.act_quit):
            f.addSeparator() if a is None else f.addAction(a)
        e = mb.addMenu("&Edit")
        for a in (self.act_undo, self.act_redo, None, self.act_add, self.act_dup, self.act_del, self.act_all):
            e.addSeparator() if a is None else e.addAction(a)
        v = mb.addMenu("&View")
        for a in (self.act_zin, self.act_zout, self.act_fit, self.act_100, None,
                  self.act_grid, self.act_snap, self.act_rulers, self.act_overlay):
            v.addSeparator() if a is None else v.addAction(a)

    def _build_toolbar(self):
        for tb in self.findChildren(QToolBar):
            tb.deleteLater()
        tb = self.addToolBar("Main")
        for a in (self.act_open, self.act_save, self.act_export_iwf):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_undo, self.act_redo, self.act_add, self.act_dup, self.act_del):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_zin, self.act_zout, self.act_fit, self.act_grid, self.act_snap):
            tb.addAction(a)
        tb.addSeparator()
        tb.addWidget(QLabel(" Device: "))
        self.device_combo = QComboBox()
        cur = self.model.project.iwf.device_id
        ids = list(VERIFIED_DEVICES)
        if cur and cur not in ids:
            ids.append(cur)       # present but its geometry is UNKNOWN unless verified
        self.device_combo.addItems(ids)
        self.device_combo.setCurrentText(cur)
        self.device_combo.currentTextChanged.connect(lambda t: self.model.set_doc_field("deviceId", t))
        tb.addWidget(self.device_combo)
        tb.addWidget(QLabel("  Grid: "))
        sp = QSpinBox(); sp.setRange(1, 200); sp.setValue(self.model.grid_spacing)
        sp.valueChanged.connect(lambda v: (setattr(self.model, "grid_spacing", v), self.model.editorStateChanged.emit()))
        tb.addWidget(sp)

    def _flag(self, name, value):
        if self.model:
            setattr(self.model, name, bool(value))
            self.model.editorStateChanged.emit()

    def _toggle_rulers(self, on):
        self.hr.setVisible(on); self.vr.setVisible(on)

    # ------------------------------------------------------------------ file ops
    def open_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Open Watch Face Project (contains iwf.json)")
        if d:
            self.open_path(d)

    def open_path(self, d):
        try:
            self.set_project(Project.open(d))
        except Exception as ex:
            QMessageBox.critical(self, "Open failed", str(ex))

    def save(self):
        if self.model:
            self.model.project.save()
            self.model.undo.setClean()
            self._update_title()

    def save_as(self):
        if not self.model:
            return
        d = QFileDialog.getExistingDirectory(self, "Save design folder as (assets are copied)")
        if not d:
            return
        import shutil
        src = self.model.project.root
        if os.path.abspath(d) != os.path.abspath(src):
            for name in os.listdir(src):
                s, t = os.path.join(src, name), os.path.join(d, name)
                if os.path.isdir(s):
                    shutil.copytree(s, t, dirs_exist_ok=True)
                elif name not in ("iwf.json", "font.json"):
                    shutil.copy2(s, t)
        self.model.project.save(d)
        self._update_title()

    def export_iwf(self):
        if not self.model:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Watch Face", self.model.project.iwf.get("name", "face") + ".iwf",
                                              "IWF Files (*.iwf)")
        if not path:
            return
        fmts = OrderedDict([("RGB565 (5)", pc.FONT_FORMAT_RGB565), ("ARGB565 (133)", pc.FONT_FORMAT_ARGB565),
                            ("BGR565 (69)", pc.FONT_FORMAT_BGR565), ("ABGR565 (197)", pc.FONT_FORMAT_ABGR565)])
        choice, ok = QInputDialog.getItem(
            self, "Choose Pixel Format",
            "WARNING: Make sure you choose the correct pixel format for your smartwatch.\nOtherwise, you'll risk boot-looping or bricking the device.", list(fmts), 0, False)
        if not ok:
            return
        try:
            n = iwf_packer.write_iwf(self.model.project.root, path, fmts[choice])
            self.statusBar().showMessage("Wrote %s (%d bytes)" % (path, n))
        except Exception as ex:
            QMessageBox.critical(self, "Export failed", str(ex))

    def export_png(self):
        if not self.model:
            return
    
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export preview PNG",
            "preview.png",
            "PNG Files (*.png)"
        )
    
        if not path:
            return
    
        try:
            # ------------------------------------------------------------------
            # Device preview profiles
            #
            # canvasWidth / canvasHeight = actual watch-face canvas dimensions
            # previewWidth / previewHeight = exported preview dimensions
            # ------------------------------------------------------------------
            DEVICE_PROFILES = {
                "IDW13": {
                    "canvasWidth": 240,
                    "canvasHeight": 284,
                    "previewWidth": 174,
                    "previewHeight": 196,
                    "previewBorderRadius": 31,
                    "previewBorderWidth": 2,
                    "previewBorderRectWidth": 168,
                    "previewBorderRectHeight": 194,
                    "previewScale": 1.0,
                    "borderColor": QColor(37, 37, 37, 255),
                },
                
                "IDW17": {
                    "canvasWidth": 240,
                    "canvasHeight": 296,
                    "previewWidth": 174,
                    "previewHeight": 196,
                    "previewBorderRadius": 38,
                    "previewBorderWidth": 2,
                    "previewBorderRectWidth": 156,
                    "previewBorderRectHeight": 192,
                    "previewScale": 0.97,
                    "borderColor": QColor(37, 37, 37, 255),
                },
    
                "IDW18": {
                    "canvasWidth": 240,
                    "canvasHeight": 240,
                    "previewWidth": 180,
                    "previewHeight": 180,
                    "previewBorderRadius": 84,
                    "previewBorderWidth": 2,
                    "previewBorderRectWidth": 169,
                    "previewBorderRectHeight": 169,
                    "previewScale": 0.94,
                    "borderColor": QColor(123, 123, 123, 255),
                },
    
                "IDW20": {
                    "canvasWidth": 320,
                    "canvasHeight": 385,
                    "previewWidth": 272,
                    "previewHeight": 324,
                    "previewBorderRadius": 67,
                    "previewBorderWidth": 3,
                    "previewBorderRectWidth": 269,
                    "previewBorderRectHeight": 321,
                    "previewScale": 0.95,
                    "borderColor": QColor(128, 128, 128, 255),
                },
                
                "ID Sport03": {
                    "canvasWidth": 240,
                    "canvasHeight": 296,
                    "previewWidth": 196,
                    "previewHeight": 238,
                    "previewBorderRadius": 50,
                    "previewBorderWidth": 2,
                    "previewBorderRectWidth": 190,
                    "previewBorderRectHeight": 232,
                    "previewScale": 0.93,
                    "borderColor": QColor(128, 128, 128, 255),
                },
            }
    
            device_id = self.model.project.iwf.device_id
    
            if device_id not in DEVICE_PROFILES:
                QMessageBox.warning(
                    self,
                    "Unsupported Device",
                    f"Preview generation is not supported for {device_id}."
                )
                return
    
            profile = DEVICE_PROFILES[device_id]
    
            # ------------------------------------------------------------------
            # Extract profile values
            # ------------------------------------------------------------------
            canvasW = profile["canvasWidth"]
            canvasH = profile["canvasHeight"]
    
            outW = profile["previewWidth"]
            outH = profile["previewHeight"]
    
            cornerRadius = profile["previewBorderRadius"]
            previewBorderWidth = profile["previewBorderWidth"]
    
            borderRectW = profile.get(
                "previewBorderRectWidth",
                outW - 4
            )
    
            borderRectH = profile.get(
                "previewBorderRectHeight",
                outH - 4
            )
    
            previewScale = profile["previewScale"]
            borderColor = profile["borderColor"]
    
            # ------------------------------------------------------------------
            # Calculate border position
            #
            # This matches the original TypeScript implementation:
            #
            # offsetX = (outW - borderRectW) / 2
            # offsetY = (outH - borderRectH) / 2
            # ------------------------------------------------------------------
            offsetX = (outW - borderRectW) / 2.0
            offsetY = (outH - borderRectH) / 2.0
    
            # ------------------------------------------------------------------
            # Render the actual watch canvas
            #
            # IMPORTANT:
            # Do NOT use QGraphicsScene.sceneRect() for canvas dimensions.
            # The scene can be larger than the actual watch-face canvas.
            #
            # The TypeScript implementation renders exactly canvasW x canvasH.
            # ------------------------------------------------------------------
            old_overlays = self.model.show_overlays
    
            try:
                self.model.show_overlays = False
                self.model.editorStateChanged.emit()
    
                scene_image = QImage(
                    canvasW,
                    canvasH,
                    QImage.Format.Format_ARGB32
                )
    
                scene_image.fill(Qt.GlobalColor.transparent)
    
                scene_painter = QPainter(scene_image)
    
                scene_painter.setRenderHint(
                    QPainter.RenderHint.Antialiasing,
                    True
                )
    
                scene_painter.setRenderHint(
                    QPainter.RenderHint.SmoothPixmapTransform,
                    True
                )
    
                # The actual watch-face coordinate space.
                source_rect = QRectF(
                    0,
                    0,
                    canvasW,
                    canvasH
                )
    
                target_rect = QRectF(
                    0,
                    0,
                    canvasW,
                    canvasH
                )
    
                self.view.scene().render(
                    scene_painter,
                    target_rect,
                    source_rect
                )
    
                scene_painter.end()
    
            finally:
                # Always restore the editor overlay state, even if rendering
                # throws an exception.
                self.model.show_overlays = old_overlays
                self.model.editorStateChanged.emit()
    
            # ------------------------------------------------------------------
            # Calculate the same scale as the original TypeScript version
            #
            # fitScale =
            #     min(outW / canvasW, outH / canvasH) * previewScale
            # ------------------------------------------------------------------
            fitScale = (
                min(
                    outW / canvasW,
                    outH / canvasH
                )
                * previewScale
            )
    
            scaledW = round(canvasW * fitScale)
            scaledH = round(canvasH * fitScale)
    
            # ------------------------------------------------------------------
            # Create final preview image
            # ------------------------------------------------------------------
            out_image = QImage(
                outW,
                outH,
                QImage.Format.Format_ARGB32
            )
    
            # Match the TypeScript implementation:
            # ctx.fillStyle = "#000000";
            # ctx.fillRect(...)
            out_image.fill(QColor(0, 0, 0, 255))
    
            painter = QPainter(out_image)
    
            painter.setRenderHint(
                QPainter.RenderHint.Antialiasing,
                True
            )
    
            painter.setRenderHint(
                QPainter.RenderHint.SmoothPixmapTransform,
                True
            )
    
            # ------------------------------------------------------------------
            # Center the scaled watch-face canvas
            #
            # Equivalent to:
            #
            # const offX = Math.floor((outW - scaledW) / 2);
            # const offY = Math.floor((outH - scaledH) / 2);
            # ------------------------------------------------------------------
            offX = int((outW - scaledW) // 2)
            offY = int((outH - scaledH) // 2)
    
            target_scaled_rect = QRect(
                offX,
                offY,
                scaledW,
                scaledH
            )
    
            painter.drawImage(
                target_scaled_rect,
                scene_image
            )
    
            # ------------------------------------------------------------------
            # Draw preview border on top
            #
            # This corresponds to:
            #
            # ctx.strokeStyle = previewBorderColor;
            # ctx.lineWidth = previewBorderWidth;
            # strokeRoundedRect(...)
            # ------------------------------------------------------------------
            pen = QPen(borderColor)
            pen.setWidth(previewBorderWidth)
    
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
    
            border_rect = QRectF(
                offsetX,
                offsetY,
                borderRectW,
                borderRectH
            )
    
            painter.drawRoundedRect(
                border_rect,
                cornerRadius,
                cornerRadius
            )
    
            painter.end()
    
            # ------------------------------------------------------------------
            # Save PNG
            # ------------------------------------------------------------------
            if not out_image.save(path, "PNG"):
                raise RuntimeError(
                    f"Failed to save PNG to {path}"
                )
    
            self.statusBar().showMessage(
                f"Wrote {path}"
            )
    
        except Exception as ex:
            QMessageBox.critical(
                self,
                "Export failed",
                str(ex)
            )
                
    def add_widget(self):
        if not self.model:
            return
        groups = [g["name"] for g in self.model.project.font.groups]
        dlg = NewWidgetDialog(groups, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        choice = dlg.result_choice()
        if choice is None:
            return
        key, font, needs_font = choice
        if needs_font and not font:
            QMessageBox.warning(self, "No glyph group chosen",
                                "This widget type is normally used with a font.json glyph group; "
                                "it will be created without one - you can add 'font'/'fontnum' "
                                "later in the Inspector.")
        n = len(self.model.project.assets.group_files(font)) if font else 0
        d = _FACTORY_BY_KEY[key](font, n)
        self.model.add_item(dict(d))

    def closeEvent(self, e):
        if self.model and self.model.project.dirty:
            r = QMessageBox.question(self, "Unsaved changes", "Save before closing?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                     QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                e.ignore(); return
            if r == QMessageBox.StandardButton.Save:
                self.save()
        e.accept()
