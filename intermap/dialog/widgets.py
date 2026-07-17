"""Small helper widgets: rich-text resize handle, drag-to-draw extent tool."""
from qgis.PyQt.QtWidgets import QWidget
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsRectangle, QgsPointXY, QgsWkbTypes
from .constants import _PURPLE


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
