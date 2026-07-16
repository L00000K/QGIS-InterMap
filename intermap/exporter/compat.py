"""
Version-tolerant QGIS imports.

Symbol-layer classes and label settings vary across QGIS releases; this
module resolves them once so the rest of the exporter can import from here.
"""
from qgis.core import QgsCoordinateReferenceSystem

# QgsSimpleMarkerSymbolLayerBase added in QGIS 3.4
try:
    from qgis.core import QgsSimpleMarkerSymbolLayerBase as _QgsSimpleMarkerBase
except ImportError:
    _QgsSimpleMarkerBase = None


def _opt_import(name):
    try:
        import qgis.core as _qc
        return getattr(_qc, name, None)
    except Exception:
        return None

_QgsGradientFill     = _opt_import("QgsGradientFillSymbolLayer")
_QgsLinePatternFill  = _opt_import("QgsLinePatternFillSymbolLayer")
_QgsPointPatternFill = _opt_import("QgsPointPatternFillSymbolLayer")
_QgsSVGFill          = _opt_import("QgsSVGFillSymbolLayer")
_QgsShapeburstFill   = _opt_import("QgsShapeburstFillSymbolLayer")
_QgsCentroidFill     = _opt_import("QgsCentroidFillSymbolLayer")

try:
    from qgis.core import QgsPalLayerSettings as _QgsPalLayerSettings
    _HAS_PAL = True
except ImportError:
    _QgsPalLayerSettings = None
    _HAS_PAL = False


_WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
