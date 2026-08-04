"""Small helper widgets: chip card, rich-text resize handle, extent tool."""
from qgis.PyQt.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsRectangle, QgsPointXY, QgsWkbTypes
from .constants import _PURPLE


class ChipCard(QFrame):
    """White card with a grey chip header — the plugin's standard section.

    The header carries the title, an optional collapse arrow and an optional
    "Include in export" checkbox. Content goes into ``body_layout``.
    """

    def __init__(self, title, collapsible=True, include_text=None, parent=None):
        super().__init__(parent)
        self.setObjectName("icCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.chip = QWidget()
        self.chip.setObjectName("icCardChip")
        chip_l = QHBoxLayout(self.chip)
        chip_l.setContentsMargins(10, 6, 10, 6)
        chip_l.setSpacing(6)

        self.toggle_btn = None
        if collapsible:
            self.toggle_btn = QPushButton("▼")
            self.toggle_btn.setObjectName("icCardToggle")
            self.toggle_btn.setFixedSize(16, 16)
            self.toggle_btn.setFlat(True)
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.setChecked(True)
            self.toggle_btn.toggled.connect(self.setExpanded)
            chip_l.addWidget(self.toggle_btn)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("icCardTitle")
        chip_l.addWidget(self.title_label, 1)

        self.include_cb = None
        if include_text is not None:
            self.include_cb = QCheckBox(include_text)
            self.include_cb.setObjectName("icCardInclude")
            self.include_cb.setChecked(True)
            chip_l.addWidget(self.include_cb)

        outer.addWidget(self.chip)

        self.body = QWidget()
        self.body.setObjectName("icCardBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 10, 12, 10)
        self.body_layout.setSpacing(6)
        outer.addWidget(self.body)

    def setExpanded(self, expanded):
        """Show or hide the body; the chip rounds off when nothing follows."""
        expanded = bool(expanded)
        self.body.setVisible(expanded)
        if self.toggle_btn is not None:
            self.toggle_btn.setText("▼" if expanded else "▶")
            if self.toggle_btn.isChecked() != expanded:
                self.toggle_btn.setChecked(expanded)
        self.chip.setProperty("collapsed", "false" if expanded else "true")
        try:
            self.chip.style().unpolish(self.chip)
            self.chip.style().polish(self.chip)
        except Exception:
            pass


class _VResizeHandle(QWidget):
    """Thin drag strip that resizes a QTextEdit vertically."""
    def __init__(self, target, min_h=50, parent=None):
        super().__init__(parent)
        self._target = target
        self._drag_y = None
        self._start_h = None
        self._min_h = min_h
        self.setFixedHeight(6)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("Drag to resize")
        self.setStyleSheet("background:#CBD5E1; border-radius:2px; margin:1px 0;")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_y = e.globalPos().y()
            self._start_h = self._target.height()

    def mouseMoveEvent(self, e):
        if self._drag_y is not None:
            delta = e.globalPos().y() - self._drag_y
            self._target.setFixedHeight(max(self._min_h, self._start_h + delta))

    def mouseReleaseEvent(self, e):
        self._drag_y = None


class _RectExtentTool:
    """Minimal wrapper that activates a rubber-band rectangle drawing tool on the
    QGIS map canvas. Calls ``callback(QgsRectangle)`` in canvas CRS on release."""

    def __init__(self, canvas, callback):
        try:
            from qgis.gui import QgsMapTool, QgsRubberBand
            from qgis.PyQt.QtCore import pyqtSignal

            class _Tool(QgsMapTool):
                rectDrawn = pyqtSignal(object)

                def __init__(self, cv):
                    super().__init__(cv)
                    self._rb = QgsRubberBand(cv, QgsWkbTypes.PolygonGeometry)
                    self._rb.setStrokeColor(QColor(_PURPLE))
                    self._rb.setFillColor(QColor(63, 50, 241, 25))
                    self._rb.setWidth(2)
                    self._start = None

                def canvasPressEvent(self, e):
                    self._start = self.toMapCoordinates(e.pos())
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)

                def canvasMoveEvent(self, e):
                    if not self._start:
                        return
                    end = self.toMapCoordinates(e.pos())
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    for pt in [
                        QgsPointXY(self._start.x(), self._start.y()),
                        QgsPointXY(self._start.x(), end.y()),
                        QgsPointXY(end.x(), end.y()),
                        QgsPointXY(end.x(), self._start.y()),
                        QgsPointXY(self._start.x(), self._start.y()),
                    ]:
                        self._rb.addPoint(pt)

                def canvasReleaseEvent(self, e):
                    if not self._start:
                        return
                    end = self.toMapCoordinates(e.pos())
                    rect = QgsRectangle(self._start, end)
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    self._start = None
                    if not rect.isEmpty():
                        self.rectDrawn.emit(rect)

                def deactivate(self):
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    super().deactivate()

            self._tool = _Tool(canvas)
            self._tool.rectDrawn.connect(callback)
            self._prev = canvas.mapTool()
            canvas.setMapTool(self._tool)
            self._canvas = canvas
        except Exception:
            self._tool = None

    def deactivate(self):
        if self._tool and self._canvas:
            try:
                self._canvas.setMapTool(self._prev)
            except Exception:
                pass
