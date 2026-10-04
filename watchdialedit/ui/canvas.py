"""FaceView: QGraphicsView showing the *export-safe* render plus editor overlays.

Layering (strict):
  * background of the scene  -> nothing
  * QGraphicsPixmapItem      -> ProjectModel.render() image ONLY (core renderer output)
  * drawForeground()         -> grid, device boundary, selection boxes, handles, snap
                                guides, rubber band.  These never enter export.
The view never stores item data: mouse edits go to ProjectModel -> iwf.json item[].
"""
from typing import List, Optional, Tuple
from PyQt6.QtCore import Qt, QRectF, QPointF, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QCursor
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QWidget)
from .qt_utils import pil_to_pixmap
from .model import ProjectModel

HANDLE_PX = 6          # on-screen handle size
SNAP_PX = 4            # on-screen snap distance
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class FaceView(QGraphicsView):
    viewChanged = pyqtSignal()

    def __init__(self, model: ProjectModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix = QGraphicsPixmapItem()
        self._pix.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._scene.addItem(self._pix)
        self.zoom = 2.0
        self._panning = False
        self._space = False
        self._last = QPointF()
        self._mode = None                  # 'move' | 'resize' | 'rubber' | None
        self._before = None
        self._origin = {}
        self._start = QPointF()
        self._handle = None
        self._rubber: Optional[QRectF] = None
        self._guides: List[Tuple[str, float]] = []
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(45, 45, 48)))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        model.changed.connect(self.refresh)
        model.selectionChanged.connect(self.viewport().update)
        model.editorStateChanged.connect(self.viewport().update)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewChanged.emit())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewChanged.emit())
        self.refresh()
        self.set_zoom(2.0)

    # ------------------------------------------------------------------ model -> view
    def face_size(self):
        img = self.model.render().image
        return img.width, img.height

    def refresh(self):
        img = self.model.render().image
        self._pix.setPixmap(pil_to_pixmap(img))
        w, h = img.size
        m = 200
        self._scene.setSceneRect(QRectF(-m, -m, w + 2 * m, h + 2 * m))
        self.viewport().update()

    def set_zoom(self, z: float):
        self.zoom = max(0.25, min(z, 32.0))
        self.resetTransform()
        self.scale(self.zoom, self.zoom)
        self.viewChanged.emit()
        self.model.editorStateChanged.emit()

    def zoom_fit(self):
        w, h = self.face_size()
        vw, vh = self.viewport().width() - 40, self.viewport().height() - 40
        self.set_zoom(max(0.25, min(vw / w, vh / h)))
        self.centerOn(w / 2, h / 2)

    # ------------------------------------------------------------------ geometry helpers
    def _boxes(self):
        return [(it.x, it.y, it.w, it.h) for it in self.model.project.iwf]

    def _sel_rect(self, idxs) -> Optional[QRectF]:
        boxes = self._boxes()
        rs = [QRectF(*boxes[i]) for i in idxs if i < len(boxes)]
        if not rs:
            return None
        r = rs[0]
        for q in rs[1:]:
            r = r.united(q)
        return r

    def hit_item(self, p: QPointF) -> Optional[int]:
        """Smallest box under the point (full-screen 'watch' widget must not swallow clicks)."""
        best, best_area = None, None
        for i, (x, y, w, h) in enumerate(self._boxes()):
            if x <= p.x() <= x + w and y <= p.y() <= y + h:
                a = w * h
                if best is None or a <= best_area:
                    best, best_area = i, a
        return best

    def _handle_rects(self, r: QRectF):
        s = HANDLE_PX / self.zoom
        cx, cy = r.center().x(), r.center().y()
        pts = {"nw": (r.left(), r.top()), "n": (cx, r.top()), "ne": (r.right(), r.top()),
               "e": (r.right(), cy), "se": (r.right(), r.bottom()), "s": (cx, r.bottom()),
               "sw": (r.left(), r.bottom()), "w": (r.left(), cy)}
        return {k: QRectF(x - s / 2, y - s / 2, s, s) for k, (x, y) in pts.items()}

    def hit_handle(self, p: QPointF) -> Optional[str]:
        if len(self.model.selection) != 1:
            return None
        r = self._sel_rect(self.model.selection)
        if r is None:
            return None
        pad = 2 / self.zoom
        for k, hr in self._handle_rects(r).items():
            if hr.adjusted(-pad, -pad, pad, pad).contains(p):
                return k
        return None

    # ------------------------------------------------------------------ snapping
    def _snap_axis(self, values, targets):
        """Return the shift (scene px) that best aligns any of `values` to `targets`."""
        thr = SNAP_PX / self.zoom
        best = None
        for v in values:
            for t in targets:
                d = t - v
                if abs(d) <= thr and (best is None or abs(d) < abs(best[0])):
                    best = (d, t)
        return best

    def _targets(self, exclude):
        w, h = self.face_size()
        xs, ys = [0, w / 2, w], [0, h / 2, h]
        for i, (x, y, bw, bh) in enumerate(self._boxes()):
            if i in exclude:
                continue
            xs += [x, x + bw / 2, x + bw]
            ys += [y, y + bh / 2, y + bh]
        return xs, ys

    def _apply_snap(self, rect: QRectF, exclude):
        """Snap a moving rect; returns (dx, dy) correction and fills self._guides."""
        self._guides = []
        if not self.model.snap_enabled:
            return 0.0, 0.0
        xs, ys = self._targets(exclude)
        g = self.model.grid_spacing
        if self.model.grid_enabled and g > 0:
            xs += [k * g for k in range(int(rect.right() // g) + 3)]
            ys += [k * g for k in range(int(rect.bottom() // g) + 3)]
        sx = self._snap_axis([rect.left(), rect.center().x(), rect.right()], xs)
        sy = self._snap_axis([rect.top(), rect.center().y(), rect.bottom()], ys)
        dx = dy = 0.0
        if sx:
            dx = sx[0]
            self._guides.append(("v", sx[1]))
        if sy:
            dy = sy[0]
            self._guides.append(("h", sy[1]))
        return dx, dy

    # ------------------------------------------------------------------ mouse / keys
    def mousePressEvent(self, e):
        self.setFocus()
        p = self.mapToScene(e.position().toPoint())
        if e.button() == Qt.MouseButton.MiddleButton or (
                e.button() == Qt.MouseButton.LeftButton and self._space):
            self._panning = True
            self._last = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        mods = e.modifiers()
        multi = bool(mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))
        h = self.hit_handle(p)
        if h:
            self._mode, self._handle = "resize", h
            self._begin_edit(p)
            return
        hit = self.hit_item(p)
        if hit is None:
            if not multi:
                self.model.select([])
            self._mode = "rubber"
            self._start = p
            self._rubber = QRectF(p, p)
            return
        sel = list(self.model.selection)
        if multi:
            sel = [i for i in sel if i != hit] if hit in sel else sel + [hit]
            self.model.select(sel)
        elif hit not in sel:
            self.model.select([hit])
        if hit in self.model.selection:
            self._mode = "move"
            self._begin_edit(p)

    def _begin_edit(self, p):
        self._before = self.model.snapshot()
        self._start = p
        self._origin = {i: (it.x, it.y, it.w, it.h)
                        for i, it in enumerate(self.model.project.iwf) if i in self.model.selection}

    def mouseMoveEvent(self, e):
        if self._panning:
            d = e.position() - self._last
            self._last = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        p = self.mapToScene(e.position().toPoint())
        if self._mode == "move":
            self._do_move(p)
        elif self._mode == "resize":
            self._do_resize(p)
        elif self._mode == "rubber":
            self._rubber = QRectF(self._start, p).normalized()
            self.viewport().update()
        else:
            self._update_cursor(p)

    def _live_apply(self, geoms):
        for i, (x, y, w, h) in geoms.items():
            self.model.project.iwf.item_at(i).set_geometry(round(x), round(y), round(w), round(h))
        self.model._render = None
        self.model.changed.emit()

    def _do_move(self, p):
        dx, dy = round(p.x() - self._start.x()), round(p.y() - self._start.y())
        union = None
        for (x, y, w, h) in self._origin.values():
            r = QRectF(x + dx, y + dy, w, h)
            union = r if union is None else union.united(r)
        sdx, sdy = self._apply_snap(union, set(self._origin))
        dx, dy = dx + round(sdx), dy + round(sdy)
        self._live_apply({i: (x + dx, y + dy, w, h) for i, (x, y, w, h) in self._origin.items()})

    def _do_resize(self, p):
        (i, (x, y, w, h)), = self._origin.items()
        left, top, right, bottom = x, y, x + w, y + h
        px, py = p.x(), p.y()
        if self.model.snap_enabled:
            xs, ys = self._targets({i})
            sx, sy = self._snap_axis([px], xs), self._snap_axis([py], ys)
            self._guides = []
            if sx and ("w" in self._handle or "e" in self._handle):
                px += sx[0]; self._guides.append(("v", sx[1]))
            if sy and ("n" in self._handle or "s" in self._handle):
                py += sy[0]; self._guides.append(("h", sy[1]))
        if "w" in self._handle: left = min(px, right - 1)
        if "e" in self._handle: right = max(px, left + 1)
        if "n" in self._handle: top = min(py, bottom - 1)
        if "s" in self._handle: bottom = max(py, top + 1)
        self._live_apply({i: (left, top, right - left, bottom - top)})

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if self._mode in ("move", "resize"):
            self.model.commit(self._before, "Move" if self._mode == "move" else "Resize")
        elif self._mode == "rubber" and self._rubber is not None:
            r = self._rubber
            hits = [i for i, (x, y, w, h) in enumerate(self._boxes())
                    if r.intersects(QRectF(x, y, w, h)) and not (w * h >= 0.9 * self._area())]
            if e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
                hits = sorted(set(hits) | set(self.model.selection))
            if r.width() > 2 or r.height() > 2:
                self.model.select(hits)
        self._mode, self._handle, self._rubber, self._guides = None, None, None, []
        self.viewport().update()

    def _area(self):
        w, h = self.face_size()
        return w * h

    def _update_cursor(self, p):
        h = self.hit_handle(p)
        cur = Qt.CursorShape.ArrowCursor
        if h in ("n", "s"): cur = Qt.CursorShape.SizeVerCursor
        elif h in ("e", "w"): cur = Qt.CursorShape.SizeHorCursor
        elif h in ("nw", "se"): cur = Qt.CursorShape.SizeFDiagCursor
        elif h in ("ne", "sw"): cur = Qt.CursorShape.SizeBDiagCursor
        elif self.hit_item(p) is not None: cur = Qt.CursorShape.SizeAllCursor
        self.setCursor(cur)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15))
        else:
            super().wheelEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self._space = True
            return
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        d = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
             Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}.get(e.key())
        if d and self.model.selection:
            before = self.model.snapshot()
            for i in self.model.selection:
                it = self.model.project.iwf.item_at(i)
                it.set_geometry(it.x + d[0], it.y + d[1])
            self.model.commit(before, "Nudge")
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.model.delete_selected()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self._space = False
        super().keyReleaseEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.viewChanged.emit()

    # ------------------------------------------------------------------ overlays only
    def drawForeground(self, painter: QPainter, rect: QRectF):
        m = self.model
        if not m.show_overlays:
            return
        w, h = self.face_size()
        painter.save()
        # device boundary
        pen = QPen(QColor(255, 255, 255, 160)); pen.setCosmetic(True); pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, 0, w, h))
        # grid (only when readable)
        g = m.grid_spacing
        if m.grid_enabled and g > 0 and g * self.zoom >= 4:
            gp = QPen(QColor(255, 255, 255, 40)); gp.setCosmetic(True)
            painter.setPen(gp)
            for x in range(0, w + 1, g):
                painter.drawLine(QPointF(x, 0), QPointF(x, h))
            for y in range(0, h + 1, g):
                painter.drawLine(QPointF(0, y), QPointF(w, y))
        # selection boxes
        sp = QPen(QColor(0, 170, 255)); sp.setCosmetic(True); sp.setWidth(1)
        painter.setPen(sp)
        for i in m.selection:
            b = self._boxes()
            if i < len(b):
                painter.drawRect(QRectF(*b[i]))
        if len(m.selection) == 1:
            r = self._sel_rect(m.selection)
            if r:
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                for hr in self._handle_rects(r).values():
                    painter.drawRect(hr)
        # snap guides
        gp = QPen(QColor(255, 0, 200)); gp.setCosmetic(True)
        painter.setPen(gp)
        for kind, v in self._guides:
            if kind == "v":
                painter.drawLine(QPointF(v, 0), QPointF(v, h))
            else:
                painter.drawLine(QPointF(0, v), QPointF(w, v))
        if self._rubber is not None:
            rp = QPen(QColor(0, 170, 255)); rp.setCosmetic(True); rp.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(rp); painter.setBrush(QBrush(QColor(0, 170, 255, 30)))
            painter.drawRect(self._rubber)
        painter.restore()


class Ruler(QWidget):
    """Pixel ruler synced to the view; purely an editor widget."""
    SIZE = 20

    def __init__(self, view: FaceView, horizontal: bool, parent=None):
        super().__init__(parent)
        self.view, self.horizontal = view, horizontal
        if horizontal:
            self.setFixedHeight(self.SIZE)
        else:
            self.setFixedWidth(self.SIZE)
        view.viewChanged.connect(self.update)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(60, 60, 64))
        p.setPen(QColor(200, 200, 200))
        z = self.view.zoom
        step = 10
        for s in (10, 20, 50, 100, 200, 500):
            step = s
            if s * z >= 40:
                break
        w, h = self.view.face_size()
        limit = (w if self.horizontal else h)
        v = 0
        while v <= limit:
            pt = self.view.mapFromScene(QPointF(v, v))
            pos = pt.x() if self.horizontal else pt.y()
            if self.horizontal:
                p.drawLine(int(pos), self.SIZE - 8, int(pos), self.SIZE)
                p.drawText(int(pos) + 2, 10, str(v))
            else:
                p.drawLine(self.SIZE - 8, int(pos), self.SIZE, int(pos))
                p.save(); p.translate(2, int(pos) + 2); p.rotate(90); p.drawText(0, 0, str(v)); p.restore()
            v += step
