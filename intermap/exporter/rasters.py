"""
Raster layer handling: legend extraction, PNG snapshot embedding, and the
quantised elevation grid used by the 3D terrain provider.
"""
import os
import base64
import tempfile
from typing import Optional

from qgis.core import (
    QgsCoordinateTransform, QgsMapSettings, QgsProject,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

from .compat import _WGS84
from .utils import _color_to_hex


def _raster_legend_data(layer) -> dict:
    """Extract legend symbology from a raster layer renderer for use in the web legend."""
    try:
        from qgis.core import (
            QgsSingleBandPseudoColorRenderer, QgsPalettedRasterRenderer,
            QgsSingleBandGrayRenderer, QgsMultiBandColorRenderer,
        )
        renderer = layer.renderer()
        if renderer is None:
            return {"type": "unknown"}

        if isinstance(renderer, QgsPalettedRasterRenderer):
            classes = []
            for cls in renderer.classes():
                classes.append({
                    "value": cls.value,
                    "label": cls.label or str(cls.value),
                    "color": _color_to_hex(cls.color),
                    "alpha": round(cls.color.alphaF(), 3),
                })
            return {"type": "paletted", "classes": classes}

        if isinstance(renderer, QgsSingleBandPseudoColorRenderer):
            shader = renderer.shader()
            if shader:
                fn = shader.rasterShaderFunction()
                if fn and hasattr(fn, "colorRampItemList"):
                    raw = fn.colorRampItemList()
                    # Thin to ≤30 stops to keep JSON compact
                    if len(raw) > 30:
                        step = len(raw) / 28
                        raw = [raw[int(i * step)] for i in range(28)] + [raw[-1]]
                    stops = [
                        {"value": round(it.value, 6),
                         "label": it.label or "",
                         "color": _color_to_hex(it.color)}
                        for it in raw
                    ]
                    return {
                        "type": "pseudocolor",
                        "stops": stops,
                        "min": stops[0]["value"] if stops else 0,
                        "max": stops[-1]["value"] if stops else 1,
                    }

        if isinstance(renderer, QgsSingleBandGrayRenderer):
            ce = renderer.contrastEnhancement()
            mn = ce.minimumValue() if ce else 0
            mx = ce.maximumValue() if ce else 255
            try:
                from qgis.core import QgsSingleBandGrayRenderer as _GR
                black_first = renderer.gradient() == _GR.BlackToWhite
            except Exception:
                black_first = True
            return {
                "type": "gray",
                "min": round(mn, 4),
                "max": round(mx, 4),
                "blackFirst": black_first,
            }

        if isinstance(renderer, QgsMultiBandColorRenderer):
            return {
                "type": "multiband",
                "redBand":   renderer.redBand(),
                "greenBand": renderer.greenBand(),
                "blueBand":  renderer.blueBand(),
            }

    except Exception:
        pass
    return {"type": "unknown"}


def _raster_to_base64(layer) -> tuple:
    """Render raster layer to PNG in WGS-84, return (base64_str, bounds_list [[s,w],[n,e]])."""
    transform = QgsCoordinateTransform(layer.crs(), _WGS84, QgsProject.instance())
    wgs_extent = transform.transformBoundingBox(layer.extent())

    width = 1024
    ratio = wgs_extent.height() / wgs_extent.width() if wgs_extent.width() > 0 else 1
    height = max(1, int(width * ratio))

    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setOutputSize(QSize(width, height))
    settings.setExtent(wgs_extent)       # render in WGS-84 so image aligns with bounds
    settings.setDestinationCrs(_WGS84)
    settings.setBackgroundColor(QColor(0, 0, 0, 0))

    from qgis.core import QgsMapRendererParallelJob
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        img.save(tmp_path, "PNG")
        with open(tmp_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    finally:
        os.unlink(tmp_path)

    bounds = [
        [wgs_extent.yMinimum(), wgs_extent.xMinimum()],
        [wgs_extent.yMaximum(), wgs_extent.xMaximum()],
    ]
    return b64, bounds


def _dem_grid_size(extent_w: float, extent_h: float, max_dim: int = 512) -> tuple:
    """Grid dimensions for a DEM sample of a max_dim budget, preserving the
    extent's aspect ratio. Both dimensions are at least 2 so the grid always
    has interpolatable corners."""
    if extent_w <= 0 or extent_h <= 0:
        return (2, 2)
    aspect = extent_w / extent_h
    if aspect >= 1.0:
        gw = max_dim
        gh = int(round(max_dim / aspect))
    else:
        gh = max_dim
        gw = int(round(max_dim * aspect))
    return (max(2, gw), max(2, gh))


def _dem_quantize(rows) -> tuple:
    """Quantize a row-major grid of heights (floats, None = nodata) to
    little-endian uint16 relative to the grid's min/max. Nodata encodes as 0
    (= the minimum height). Returns (vmin, vmax, bytes)."""
    vals = [v for row in rows for v in row if v is not None]
    if not vals:
        n = sum(len(row) for row in rows)
        return (0.0, 0.0, b"\x00\x00" * n)
    vmin = float(min(vals))
    vmax = float(max(vals))
    rng = (vmax - vmin) or 1.0
    out = bytearray()
    for row in rows:
        for v in row:
            if v is None:
                q = 0
            else:
                q = int(round((v - vmin) / rng * 65535))
                q = 0 if q < 0 else (65535 if q > 65535 else q)
            out += q.to_bytes(2, "little")
    return (vmin, vmax, bytes(out))


def _build_elevation_dem(layer, max_dim: int = 512) -> Optional[dict]:
    """Sample a QGIS raster layer (band 1) into a WGS-84 height grid for the
    Cesium terrain provider. Row 0 is the northern edge, matching Cesium's
    heightmap convention. Returns a JSON-able dict, or None if the raster
    cannot be sampled — the export then simply carries no terrain."""
    try:
        from qgis.core import QgsPointXY

        provider = layer.dataProvider()
        ext = layer.extent()
        if ext.width() <= 0 or ext.height() <= 0:
            return None
        tr_fwd = QgsCoordinateTransform(layer.crs(), _WGS84, QgsProject.instance())
        wgs = tr_fwd.transformBoundingBox(ext)
        if wgs.width() <= 0 or wgs.height() <= 0:
            return None
        gw, gh = _dem_grid_size(wgs.width(), wgs.height(), max_dim)

        # One resampled read of the source band in the layer's own CRS, then
        # index into it per grid point — far faster than per-point sample().
        bw = min(int(provider.xSize() or 0) or 1024, 1024)
        bh = min(int(provider.ySize() or 0) or 1024, 1024)
        block = provider.block(1, ext, bw, bh)

        same_crs = layer.crs().authid() == _WGS84.authid()
        tr_back = None if same_crs else QgsCoordinateTransform(
            _WGS84, layer.crs(), QgsProject.instance())

        rows = []
        for j in range(gh):
            lat = wgs.yMaximum() - (wgs.yMaximum() - wgs.yMinimum()) * (j / (gh - 1))
            row = []
            for i in range(gw):
                lon = wgs.xMinimum() + (wgs.xMaximum() - wgs.xMinimum()) * (i / (gw - 1))
                if same_crs:
                    px, py = lon, lat
                else:
                    try:
                        p = tr_back.transform(QgsPointXY(lon, lat))
                        px, py = p.x(), p.y()
                    except Exception:
                        row.append(None)
                        continue
                col = int((px - ext.xMinimum()) / ext.width() * bw)
                rw  = int((ext.yMaximum() - py) / ext.height() * bh)
                if col < 0 or rw < 0 or col >= bw or rw >= bh or block.isNoData(rw, col):
                    row.append(None)
                else:
                    row.append(float(block.value(rw, col)))
            rows.append(row)

        vmin, vmax, raw = _dem_quantize(rows)
        return {
            "b64":   base64.b64encode(raw).decode("ascii"),
            "w":     gw, "h": gh,
            "min":   vmin, "max": vmax,
            "west":  wgs.xMinimum(), "south": wgs.yMinimum(),
            "east":  wgs.xMaximum(), "north": wgs.yMaximum(),
        }
    except Exception as e:
        print(f"InterMap: elevation raster skipped ({e})")
        return None


# ── Report / story-mode helpers ──────────────────────────────────────────────
