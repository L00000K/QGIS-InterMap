"""Parsing QGIS raster data sources that stay remote: WMS/WMTS/XYZ and COGs."""
import re
from urllib.parse import parse_qs
from typing import Optional

from qgis.core import QgsCoordinateTransform, QgsProject

from .compat import _WGS84


def _parse_wms_source(layer) -> Optional[dict]:
    """
    If layer is a WMS/WMTS raster layer, return a dict describing how to
    add it in Leaflet. Returns None for plain file-based rasters.
    """
    provider = layer.dataProvider()
    if provider is None or provider.name() != "wms":
        return None

    uri_str = provider.dataSourceUri()
    params  = parse_qs(uri_str, keep_blank_values=True)

    url = (params.get("url") or params.get("URL") or [None])[0]
    if not url:
        return None

    layers  = (params.get("layers")  or [""])[0]
    format_ = (params.get("format")  or ["image/png"])[0]
    styles  = (params.get("styles")  or [""])[0]
    crs     = (params.get("crs") or params.get("CRS") or
               params.get("srs") or params.get("SRS") or ["EPSG:3857"])[0]
    version = (params.get("version") or ["1.1.1"])[0]

    # WMTS / XYZ tile layers embed the tile URL template directly
    ttype = (params.get("type") or ["wms"])[0].lower()

    return {
        "wmsUrl":     url,
        "wmsLayers":  layers,
        "wmsFormat":  format_,
        "wmsStyles":  styles,
        "wmsCrs":     crs,
        "wmsVersion": version,
        "tileType":   ttype,
    }


def _parse_cog_source(layer) -> Optional[dict]:
    """
    If a GDAL raster layer's source is a remote HTTP(S) Cloud Optimized
    GeoTIFF (e.g. a topography raster on public Azure blob storage), return a
    dict describing how to load it client-side rather than embedding it as
    base64. Returns None for local files and non-COG sources.

    QGIS represents a remote COG through GDAL's virtual filesystem, e.g.
        /vsicurl/https://acct.blob.core.windows.net/container/dem.tif
    or occasionally as a bare https URL. We pull the first http(s) URL out of
    the source URI and keep it only when it points at a .tif/.tiff.
    """
    provider = layer.dataProvider()
    if provider is None or provider.name() != "gdal":
        return None

    uri = provider.dataSourceUri() or ""
    m = re.search(r"https?://\S+", uri)
    if not m:
        return None
    url = m.group(0)
    # Trim trailing GDAL open-option delimiters (|) or whitespace-separated args
    for sep in ("|", " ", "\t"):
        if sep in url:
            url = url.split(sep)[0]

    low = url.lower()
    if not (low.endswith(".tif") or low.endswith(".tiff")
            or ".tif?" in low or ".tiff?" in low):
        return None

    ext = layer.extent()
    tr  = QgsCoordinateTransform(layer.crs(), _WGS84, QgsProject.instance())
    wgs = tr.transformBoundingBox(ext)
    return {
        "kind":    "cog",
        "name":    layer.name(),
        "url":     url,
        "opacity": round(layer.opacity(), 3),
        "bands":   layer.bandCount() if hasattr(layer, "bandCount") else 0,
        "bounds": [
            [wgs.yMinimum(), wgs.xMinimum()],
            [wgs.yMaximum(), wgs.xMaximum()],
        ],
    }


def _wms_legend_url(wms: dict) -> str:
    """Build a GetLegendGraphic URL from a WMS params dict, or '' if not possible."""
    base = wms.get("wmsUrl", "")
    if not base or wms.get("tileType", "wms") != "wms":
        return ""
    from urllib.parse import urlencode
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetLegendGraphic",
        "VERSION": wms.get("wmsVersion", "1.1.1"),
        "LAYER": wms.get("wmsLayers", ""),
        "FORMAT": "image/png",
    }
    style = wms.get("wmsStyles", "")
    if style:
        params["STYLE"] = style
    sep = "&" if "?" in base else "?"
    return base + sep + urlencode(params)
