"""Qt5/Qt6 and QGIS 3/4 differences, resolved once at import.

QGIS 4 moves to Qt6, and PyQt6 is stricter than PyQt5 in three ways that reach
this plugin: enum members must be fully scoped, ``exec_()`` is gone, and
``QAction`` lives in QtGui rather than QtWidgets. Scoped enums and ``exec()``
work on PyQt5 too, so those are simply spelled the Qt6 way throughout and need
nothing here.

QGIS 4 also drops long-deprecated enum aliases. The names below resolve to the
modern spelling where the running QGIS has it and fall back to the old one on
QGIS 3.28, which is still the declared minimum.
"""

__all__ = [
    "QAction",
    "LAYER_TYPE_VECTOR", "LAYER_TYPE_RASTER", "GEOMETRY_TYPE_POLYGON",
    "MESSAGE_WARNING", "event_global_pos", "event_pos",
]

# ── QAction: QtWidgets in Qt5, QtGui in Qt6 ─────────────────────────────────
try:
    from qgis.PyQt.QtGui import QAction          # Qt6
except ImportError:                              # pragma: no cover - Qt5 path
    from qgis.PyQt.QtWidgets import QAction


def _first_attr(obj, *names):
    """First attribute of `obj` that exists, by dotted name. None if none do."""
    for name in names:
        target = obj
        try:
            for part in name.split("."):
                target = getattr(target, part)
        except AttributeError:
            continue
        return target
    return None


# ── Layer and geometry types ────────────────────────────────────────────────
# Qgis.LayerType / Qgis.GeometryType arrived in QGIS 3.30 and are the only
# spelling in 4.x; QgsMapLayer.VectorLayer and QgsWkbTypes.PolygonGeometry are
# the 3.x aliases.
try:
    from qgis.core import Qgis
except Exception:                                # pragma: no cover
    Qgis = None

try:
    from qgis.core import QgsMapLayer
except Exception:                                # pragma: no cover
    QgsMapLayer = None

try:
    from qgis.core import QgsWkbTypes
except Exception:                                # pragma: no cover
    QgsWkbTypes = None

LAYER_TYPE_VECTOR = (_first_attr(Qgis, "LayerType.Vector")
                     if Qgis is not None else None)
if LAYER_TYPE_VECTOR is None:                    # pragma: no cover - QGIS 3.28
    LAYER_TYPE_VECTOR = _first_attr(QgsMapLayer, "VectorLayer")

LAYER_TYPE_RASTER = (_first_attr(Qgis, "LayerType.Raster")
                     if Qgis is not None else None)
if LAYER_TYPE_RASTER is None:                    # pragma: no cover - QGIS 3.28
    LAYER_TYPE_RASTER = _first_attr(QgsMapLayer, "RasterLayer")

GEOMETRY_TYPE_POLYGON = (_first_attr(Qgis, "GeometryType.Polygon")
                         if Qgis is not None else None)
if GEOMETRY_TYPE_POLYGON is None:                # pragma: no cover - QGIS 3.28
    GEOMETRY_TYPE_POLYGON = _first_attr(QgsWkbTypes, "PolygonGeometry")

# ── Message bar level ───────────────────────────────────────────────────────
MESSAGE_WARNING = (_first_attr(Qgis, "MessageLevel.Warning", "Warning")
                   if Qgis is not None else None)


# ── Mouse events ────────────────────────────────────────────────────────────
# Qt6 deprecates the integer-point accessors in favour of QPointF ones. Both
# exist in Qt5, so prefer the new names and fall back only if they are absent.
def event_global_pos(event):
    """Global position of a mouse event as a QPoint, on either Qt."""
    getter = getattr(event, "globalPosition", None)
    if getter is not None:
        return getter().toPoint()
    return event.globalPos()                     # pragma: no cover - Qt5 path


def event_pos(event):
    """Widget-local position of a mouse event as a QPoint, on either Qt."""
    getter = getattr(event, "position", None)
    if getter is not None:
        return getter().toPoint()
    return event.pos()                           # pragma: no cover - Qt5 path
