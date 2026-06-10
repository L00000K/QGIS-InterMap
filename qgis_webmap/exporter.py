import os
import json
import base64
import tempfile
import urllib.request
from urllib.parse import parse_qs

from qgis.core import (
    QgsMapLayer, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsProject, QgsRenderContext,
    QgsFeatureRequest, QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsGraduatedSymbolRenderer, QgsRuleBasedRenderer,
    QgsSymbol, QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsSvgMarkerSymbolLayer,
    QgsUnitTypes, QgsMapSettings, QgsRectangle
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize, QUrl, Qt
from qgis.PyQt.QtNetwork import QNetworkRequest

# QgsSimpleMarkerSymbolLayerBase added in QGIS 3.4
try:
    from qgis.core import QgsSimpleMarkerSymbolLayerBase as _QgsSimpleMarkerBase
except ImportError:
    _QgsSimpleMarkerBase = None

try:
    from qgis.core import QgsPalLayerSettings as _QgsPalLayerSettings
    _HAS_PAL = True
except ImportError:
    _QgsPalLayerSettings = None
    _HAS_PAL = False


_WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

_PLUGIN_DIR      = os.path.dirname(__file__)
_LIB_DIR         = os.path.join(_PLUGIN_DIR, "lib")
_LEAFLET_VERSION = "1.9.4"
_LEAFLET_URLS = [
    "https://unpkg.com/leaflet@{v}/dist/leaflet.min.{ext}",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/{v}/leaflet.min.{ext}",
]


def _qgis_fetch(url_str: str) -> str | None:
    """
    Download text from url_str using QGIS's network stack (respects proxy /
    auth settings configured in QGIS options) with a fallback to urllib.
    Returns the decoded text or None on failure.
    """
    # QgsBlockingNetworkRequest available since QGIS 3.6
    try:
        from qgis.core import QgsBlockingNetworkRequest
        req = QNetworkRequest(QUrl(url_str))
        blocker = QgsBlockingNetworkRequest()
        err = blocker.get(req)
        if err == QgsBlockingNetworkRequest.NoError:
            return bytes(blocker.reply().content()).decode("utf-8")
    except Exception:
        pass

    # Plain urllib fallback
    try:
        with urllib.request.urlopen(url_str, timeout=20) as r:
            return r.read().decode("utf-8")
    except Exception:
        pass

    return None


_VENDOR_CSS = os.path.join(_PLUGIN_DIR, "vendor", "leaflet.css")
_VENDOR_JS  = os.path.join(_PLUGIN_DIR, "vendor", "leaflet.js")


def _get_leaflet_assets() -> tuple[str, str] | tuple[None, None]:
    """
    Return (css, js) strings for inline embedding.

    Priority:
      1. Bundled vendor/ files shipped with the plugin (always available).
      2. Previously downloaded + cached copy in lib/.
      3. Download from CDN and cache in lib/.
      4. Return (None, None) — caller falls back to CDN <link>/<script> tags.
    """
    # 1. Bundled files — committed to the repo, always present
    if os.path.exists(_VENDOR_CSS) and os.path.exists(_VENDOR_JS):
        with open(_VENDOR_CSS, encoding="utf-8") as f:
            css = f.read()
        with open(_VENDOR_JS, encoding="utf-8") as f:
            js = f.read()
        return css, js

    # 2. Previously cached download
    v        = _LEAFLET_VERSION
    css_path = os.path.join(_LIB_DIR, f"leaflet-{v}.min.css")
    js_path  = os.path.join(_LIB_DIR, f"leaflet-{v}.min.js")
    if os.path.exists(css_path) and os.path.exists(js_path):
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        with open(js_path, encoding="utf-8") as f:
            js = f.read()
        return css, js

    # 3. Download and cache
    os.makedirs(_LIB_DIR, exist_ok=True)
    for tpl in _LEAFLET_URLS:
        css = _qgis_fetch(tpl.format(v=v, ext="css"))
        js  = _qgis_fetch(tpl.format(v=v, ext="js"))
        if css and js:
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(css)
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(js)
            return css, js

    return None, None


# ── Plugin asset specs ────────────────────────────────────────────────────────
_PLUGIN_SPECS = {
    "fullscreen":    ("fullscreen.min.css",  "fullscreen.min.js"),
    "minimap":       ("minimap.min.css",     "minimap.min.js"),
    "search":        ("search.min.css",      "search.min.js"),
    "contextmenu":   ("contextmenu.min.css", "contextmenu.min.js"),
    "geoman":        ("geoman.min.css",      "geoman.min.js"),
    "markercluster": ("markercluster.css",   "markercluster.js"),
}


def _load_plugin_assets() -> dict:
    """
    Return {name: (css_str, js_str)} for each plugin whose vendor files exist.
    Missing plugins degrade silently — JS guards (typeof checks) handle absence.
    """
    vendor = os.path.join(_PLUGIN_DIR, "vendor")
    result = {}
    for name, (css_file, js_file) in _PLUGIN_SPECS.items():
        css_path = os.path.join(vendor, css_file)
        js_path  = os.path.join(vendor, js_file)
        if os.path.exists(css_path) and os.path.exists(js_path):
            with open(css_path, encoding="utf-8") as f:
                css = f.read()
            with open(js_path, encoding="utf-8") as f:
                js = f.read()
            result[name] = (css, js)
    return result


def _parse_wms_source(layer) -> dict | None:
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


def _color_to_hex(color: QColor) -> str:
    return "#{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue())


def _color_to_rgba(color: QColor) -> str:
    return "rgba({},{},{},{:.3f})".format(
        color.red(), color.green(), color.blue(), color.alphaF()
    )


def _size_to_px(size: float, unit) -> float:
    """Convert a QGIS symbol size in its render unit to approximate pixels (96 DPI)."""
    try:
        if unit == QgsUnitTypes.RenderPixels:
            return size
        if unit == QgsUnitTypes.RenderPoints:
            return size * 96.0 / 72.0
        if unit == QgsUnitTypes.RenderInches:
            return size * 96.0
        # Millimeters (QGIS default) and everything else
        return size * 96.0 / 25.4
    except Exception:
        # Fallback assuming millimeters
        return size * 96.0 / 25.4


# Map QGIS marker shape names to a small set the web map can draw.
_SHAPE_ALIASES = {
    "square": "square",
    "rectangle": "square",
    "square_with_corners": "square",
    "rounded_square": "square",
    "diamond": "diamond",
    "triangle": "triangle",
    "equilateral_triangle": "triangle",
    "star": "star",
    "regular_star": "star",
    "pentagon": "pentagon",
    "hexagon": "hexagon",
    "octagon": "octagon",
    "cross": "cross",
    "cross2": "x",
    "x": "x",
    "cross_fill": "square",
    "circle": "circle",
}


def _encode_marker_shape(sl) -> str:
    """Return a normalized shape name string for a simple marker symbol layer."""
    try:
        if _QgsSimpleMarkerBase is None:
            return "circle"
        raw = _QgsSimpleMarkerBase.encodeShape(sl.shape())
        return _SHAPE_ALIASES.get(str(raw).lower(), "circle")
    except Exception:
        return "circle"


def _extract_label_config(layer) -> dict | None:
    """Extract label settings from a vector layer. Returns None if no label field is set."""
    if not _HAS_PAL:
        return None
    try:
        if not hasattr(layer, "labeling") or layer.labeling() is None:
            return None
        labeling = layer.labeling()
        if not hasattr(labeling, "settings"):
            return None
        settings = labeling.settings()
        field = settings.fieldName
        if not field:
            return None
        fmt = settings.format()
        font = fmt.font()
        color = fmt.color()
        font_px = max(8, round(_size_to_px(fmt.size(), fmt.sizeUnit())))
        cfg: dict = {
            "field":       field,
            "isExpr":      bool(settings.isExpression),
            "enabled":     bool(layer.labelsEnabled()),
            "fontSize":    font_px,
            "fontColor":   _color_to_hex(color),
            "fontOpacity": round(float(fmt.opacity()), 3),
            "fontFamily":  font.family() or "sans-serif",
            "bold":        bool(font.bold()),
            "italic":      bool(font.italic()),
        }
        buf = fmt.buffer()
        if hasattr(buf, "enabled") and buf.enabled():
            bc = buf.color()
            cfg["bufferSize"]  = max(1, round(_size_to_px(buf.size(), buf.sizeUnit())))
            cfg["bufferColor"] = _color_to_hex(bc)
        return cfg
    except Exception:
        return None


def _extract_symbol_style(symbol) -> dict:
    """Extract Leaflet path/marker style from a QGIS symbol."""
    style = {}
    if symbol is None:
        return style

    geom_type = symbol.type()  # 0=marker, 1=line, 2=fill

    # Symbol-level opacity (separate from per-colour alpha in QGIS)
    try:
        sym_opacity = float(symbol.opacity())
    except Exception:
        sym_opacity = 1.0

    # Walk symbol layers to find the primary paint layer
    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)

        if isinstance(sl, QgsSimpleFillSymbolLayer):
            fill_color = sl.fillColor()
            stroke_color = sl.strokeColor()
            style["fillColor"] = _color_to_hex(fill_color)
            style["fillOpacity"] = round(fill_color.alphaF() * sym_opacity, 3)
            try:
                no_border = sl.strokeStyle() == Qt.NoPen
            except Exception:
                no_border = False
            if no_border:
                style["color"] = _color_to_hex(fill_color)
                style["opacity"] = 0.0
                style["weight"] = 0
            else:
                style["color"] = _color_to_hex(stroke_color)
                style["opacity"] = round(stroke_color.alphaF() * sym_opacity, 3)
                style["weight"] = round(max(0.0, _size_to_px(sl.strokeWidth(), sl.strokeWidthUnit())), 1) or 1
            break

        elif isinstance(sl, QgsSimpleLineSymbolLayer):
            color = sl.color()
            style["color"] = _color_to_hex(color)
            style["opacity"] = round(color.alphaF() * sym_opacity, 3)
            style["weight"] = round(max(0.5, _size_to_px(sl.width(), sl.widthUnit())), 1)
            style["fillOpacity"] = 0
            try:
                pen = sl.penStyle()
                if pen == Qt.DashLine:
                    style["dashArray"] = "8 4"
                elif pen == Qt.DotLine:
                    style["dashArray"] = "2 4"
                elif pen == Qt.DashDotLine:
                    style["dashArray"] = "8 4 2 4"
                elif pen == Qt.DashDotDotLine:
                    style["dashArray"] = "8 4 2 4 2 4"
                elif pen == Qt.CustomDashLine:
                    dv = sl.customDashVector()
                    unit = sl.customDashPatternUnit()
                    parts = [str(round(_size_to_px(v, unit), 1)) for v in dv]
                    if parts:
                        style["dashArray"] = " ".join(parts)
            except Exception:
                pass
            break

        elif isinstance(sl, QgsSimpleMarkerSymbolLayer):
            color = sl.color()
            stroke_color = sl.strokeColor()
            style["markerColor"] = _color_to_hex(color)
            style["markerOpacity"] = round(color.alphaF() * sym_opacity, 3)
            style["markerStrokeColor"] = _color_to_hex(stroke_color)
            style["markerStrokeOpacity"] = round(stroke_color.alphaF() * sym_opacity, 3)
            try:
                no_stroke = sl.strokeStyle() == Qt.NoPen
            except Exception:
                no_stroke = False
            if no_stroke:
                style["markerStrokeWidth"] = 0
            else:
                try:
                    sw_px = _size_to_px(sl.strokeWidth(), sl.strokeWidthUnit())
                except Exception:
                    sw_px = 1.0
                style["markerStrokeWidth"] = round(max(0.5, sw_px), 1)
            style["markerSize"] = max(4, round(_size_to_px(sl.size(), sl.sizeUnit())))
            style["markerShape"] = _encode_marker_shape(sl)
            try:
                style["markerAngle"] = round(sl.angle(), 1)
            except Exception:
                style["markerAngle"] = 0
            break

        elif isinstance(sl, QgsSvgMarkerSymbolLayer):
            color = sl.fillColor()
            style["markerColor"] = _color_to_hex(color)
            style["markerOpacity"] = round(color.alphaF() * sym_opacity, 3)
            try:
                style["markerStrokeColor"] = _color_to_hex(sl.strokeColor())
            except Exception:
                pass
            style["markerSize"] = max(4, round(_size_to_px(sl.size(), sl.sizeUnit())))
            style["markerShape"] = "circle"
            break

    # Defaults for fill polygons if nothing matched
    if geom_type == QgsSymbol.Fill and "fillColor" not in style:
        c = symbol.color()
        style["fillColor"] = _color_to_hex(c)
        style["fillOpacity"] = round(c.alphaF(), 3)
        style["color"] = "#000000"
        style["weight"] = 1
        style["opacity"] = 1

    elif geom_type == QgsSymbol.Line and "color" not in style:
        c = symbol.color()
        style["color"] = _color_to_hex(c)
        style["opacity"] = round(c.alphaF(), 3)
        style["weight"] = 2
        style["fillOpacity"] = 0

    elif geom_type == QgsSymbol.Marker and "markerColor" not in style:
        c = symbol.color()
        style["markerColor"] = _color_to_hex(c)
        style["markerOpacity"] = round(c.alphaF(), 3)
        style["markerSize"] = 8

    return style


def _build_style_map(layer) -> dict:
    """
    Returns a dict describing how to style the layer in JS.

    Common shape:
      type: 'single' | 'categorized' | 'graduated' | 'rule'
      entries: list of legend items (for multi-symbol renderers)
      style: {...}   (for single)
      field: str     (for categorized / graduated)
      default: {...}
    """
    renderer = layer.renderer()
    if renderer is None:
        return {"type": "single", "style": {}}

    if isinstance(renderer, QgsSingleSymbolRenderer):
        return {
            "type": "single",
            "style": _extract_symbol_style(renderer.symbol()),
        }

    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        entries = []
        for cat in renderer.categories():
            raw_val = cat.value()
            # Preserve None as JSON null so JS can match null feature properties
            entry_val = None if raw_val is None else str(raw_val)
            entries.append({
                "value": entry_val,
                "label": cat.label() or (str(raw_val) if raw_val is not None else "(no value)"),
                "style": _extract_symbol_style(cat.symbol()),
            })
        return {
            "type": "categorized",
            "field": renderer.classAttribute(),
            "entries": entries,
            "default": {},
        }

    if isinstance(renderer, QgsGraduatedSymbolRenderer):
        entries = []
        for r in renderer.ranges():
            entries.append({
                "min": r.lowerValue(),
                "max": r.upperValue(),
                "label": r.label() or f"{r.lowerValue()} – {r.upperValue()}",
                "style": _extract_symbol_style(r.symbol()),
            })
        return {
            "type": "graduated",
            "field": renderer.classAttribute(),
            "entries": entries,
            "default": {},
        }

    if isinstance(renderer, QgsRuleBasedRenderer):
        entries = []
        for rule in renderer.rootRule().children():
            entries.append({
                "label": rule.label() or "Rule",
                "style": _extract_symbol_style(rule.symbol()),
            })
        return {
            "type": "rule",
            "entries": entries,
            "default": entries[0]["style"] if entries else {},
        }

    # Fallback
    return {"type": "single", "style": {}}


def _layer_to_geojson(layer) -> dict:
    """Reproject and convert vector layer to GeoJSON dict."""
    transform = QgsCoordinateTransform(
        layer.crs(), _WGS84, QgsProject.instance()
    )

    features = []
    for feat in layer.getFeatures(QgsFeatureRequest()):
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            props = {k: (str(v) if v is not None else None) for k, v in feat.attributeMap().items()}
            features.append({"type": "Feature", "geometry": None, "properties": props})
            continue

        geom.transform(transform)
        geom_json = json.loads(geom.asJson())

        props = {}
        fields = layer.fields()
        for i, attr in enumerate(feat.attributes()):
            fname = fields[i].name()
            if attr is None:
                props[fname] = None
            elif isinstance(attr, (int, float, bool)):
                props[fname] = attr
            else:
                props[fname] = str(attr)

        features.append({
            "type": "Feature",
            "geometry": geom_json,
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}


def _raster_to_base64(layer) -> tuple:
    """Render raster layer to PNG, return (base64_str, bounds_list [[s,w],[n,e]])."""
    extent = layer.extent()
    transform = QgsCoordinateTransform(layer.crs(), _WGS84, QgsProject.instance())
    wgs_extent = transform.transformBoundingBox(extent)

    width = 1024
    ratio = extent.height() / extent.width() if extent.width() > 0 else 1
    height = max(1, int(width * ratio))

    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setOutputSize(QSize(width, height))
    settings.setExtent(extent)
    settings.setDestinationCrs(layer.crs())
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


def _geom_type_str(layer) -> str:
    wkb = layer.wkbType()
    flat = QgsWkbTypes.flatType(wkb)
    if flat in (QgsWkbTypes.Point, QgsWkbTypes.MultiPoint):
        return "point"
    if flat in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
        return "line"
    return "polygon"


class WebMapExporter:
    def __init__(self, layers, output_path,
                 include_layer_control=True, include_basemap=True,
                 progress_callback=None,
                 layer_tree=None, initial_extent=None, map_views=None,
                 info_panel=None):
        self.layers = layers
        self.output_path = output_path
        self.include_layer_control = include_layer_control
        self.include_basemap = include_basemap
        self.progress = progress_callback or (lambda v: None)
        self.layer_tree = layer_tree or []
        self.initial_extent = initial_extent
        self.map_views = map_views or []
        self.info_panel = info_panel or {}

    def export(self):
        layer_defs = []
        step = 0

        for layer in self.layers:
            step += 1
            self.progress(step)

            if layer.type() == QgsMapLayer.VectorLayer:
                geojson = _layer_to_geojson(layer)
                style_map = _build_style_map(layer)
                geom_type = _geom_type_str(layer)
                ldef: dict = {
                    "kind":     "vector",
                    "name":     layer.name(),
                    "geomType": geom_type,
                    "geojson":  geojson,
                    "styleMap": style_map,
                }
                label_cfg = _extract_label_config(layer)
                if label_cfg:
                    ldef["labelConfig"] = label_cfg
                layer_defs.append(ldef)

            elif layer.type() == QgsMapLayer.RasterLayer:
                wms = _parse_wms_source(layer)
                if wms:
                    # Reproject layer extent to WGS-84 for fitBounds
                    ext = layer.extent()
                    tr  = QgsCoordinateTransform(layer.crs(), _WGS84, QgsProject.instance())
                    wgs = tr.transformBoundingBox(ext)
                    layer_defs.append({
                        "kind":   "wms",
                        "name":   layer.name(),
                        "bounds": [
                            [wgs.yMinimum(), wgs.xMinimum()],
                            [wgs.yMaximum(), wgs.xMaximum()],
                        ],
                        **wms,
                    })
                else:
                    b64, bounds = _raster_to_base64(layer)
                    layer_defs.append({
                        "kind":   "raster",
                        "name":   layer.name(),
                        "data":   b64,
                        "bounds": bounds,
                    })

        self.progress(step + 1)

        # Compute overall bounds for map fitBounds
        all_bounds = self._overall_bounds(layer_defs)

        html = self._render_html(layer_defs, all_bounds)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _overall_bounds(self, layer_defs):
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for ld in layer_defs:
            if ld["kind"] in ("raster", "wms"):
                b = ld["bounds"]
                min_y = min(min_y, b[0][0])
                min_x = min(min_x, b[0][1])
                max_y = max(max_y, b[1][0])
                max_x = max(max_x, b[1][1])
            elif ld["kind"] == "vector":
                for feat in ld["geojson"]["features"]:
                    geom = feat.get("geometry")
                    if geom is None:
                        continue
                    for coord in _flatten_coords(geom):
                        min_x = min(min_x, coord[0])
                        min_y = min(min_y, coord[1])
                        max_x = max(max_x, coord[0])
                        max_y = max(max_y, coord[1])
        if min_x == float("inf"):
            return [[51.5, -0.1], [51.5, -0.1]]  # fallback: London
        return [[min_y, min_x], [max_y, max_x]]

    def _render_html(self, layer_defs, bounds) -> str:
        # Escape </script> in embedded JSON so it can't break the <script> block
        layers_json = json.dumps(layer_defs, separators=(",", ":")).replace(
            "</", "<\\/"
        )
        bounds_json = json.dumps(bounds)
        initial_bounds = self.initial_extent if self.initial_extent else bounds
        initial_bounds_json = json.dumps(initial_bounds)
        include_legend = "true" if self.include_layer_control else "false"
        include_basemap_json = "true" if self.include_basemap else "false"
        tree_json = json.dumps(self.layer_tree, separators=(",", ":")).replace("</", "<\\/")
        themes_json = json.dumps(self.map_views, separators=(",", ":")).replace("</", "<\\/")

        import html as _html_mod
        _info = self.info_panel
        _info_enabled = bool(_info.get("enabled", False))
        _info_title = _html_mod.escape(str(_info.get("title", "") or ""))
        _info_text = _html_mod.escape(str(_info.get("text", "") or ""))
        _info_date = _html_mod.escape(str(_info.get("date", "") or ""))
        _info_client = _html_mod.escape(str(_info.get("client", "") or ""))
        _info_project = _html_mod.escape(str(_info.get("project", "") or ""))
        _doc_control = [
            ("Originated", _html_mod.escape(str(_info.get("originated_name", "") or "")),
                           _html_mod.escape(str(_info.get("originated_date", "") or ""))),
            ("Checked",    _html_mod.escape(str(_info.get("checked_name", "") or "")),
                           _html_mod.escape(str(_info.get("checked_date", "") or ""))),
            ("Reviewed",   _html_mod.escape(str(_info.get("reviewed_name", "") or "")),
                           _html_mod.escape(str(_info.get("reviewed_date", "") or ""))),
            ("Approved",   _html_mod.escape(str(_info.get("approved_name", "") or "")),
                           _html_mod.escape(str(_info.get("approved_date", "") or ""))),
        ]
        _page_title = _html_mod.escape(_info.get("title", "") or "QGIS Web Map")

        leaflet_css, leaflet_js = _get_leaflet_assets()
        if leaflet_css and leaflet_js:
            leaflet_head = (
                f"<style>\n{leaflet_css}\n</style>\n"
                f"<script>\n{leaflet_js}\n</script>"
            )
        else:
            # CDN fallback — requires internet access when the HTML is opened
            leaflet_head = (
                '<link rel="stylesheet"'
                ' href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"'
                ' crossorigin=""/>\n'
                '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"'
                ' crossorigin=""></script>'
            )

        # Plugin assets — each is optional; JS typeof guards handle absence
        _plugins = _load_plugin_assets()

        def _plugin_block(name: str) -> str:
            if name not in _plugins:
                return ""
            css, js = _plugins[name]
            return (
                "<style>\n" + css + "\n</style>\n"
                "<script>\n" + js.replace("</", "<\\/") + "\n</script>"
            )

        plugin_heads = "\n".join(filter(bool, [
            _plugin_block("markercluster"),
            _plugin_block("fullscreen"),
            _plugin_block("minimap"),
            _plugin_block("contextmenu"),
        ]))

        # Brand watermark — prefer logo.svg (case-insensitive), fall back to logo.png, then built-in SVG
        import base64 as _b64
        _logo_svg = None
        for _svgname in ("Logo.svg", "logo.svg"):
            _svgpath = os.path.join(_PLUGIN_DIR, "vendor", _svgname)
            if os.path.exists(_svgpath):
                _logo_svg = _svgpath
                break
        _logo_png  = os.path.join(_PLUGIN_DIR, "vendor", "logo.png")
        if _logo_svg is not None:
            with open(_logo_svg, encoding="utf-8") as _f:
                _svg_src = _f.read().strip()
            # Wrap in a sized container so height is constrained
            brand_content = (
                f'<span style="height:22px;display:flex;align-items:center;">'
                f'{_svg_src}</span>'
            )
        elif os.path.exists(_logo_png):
            import base64 as _b64
            with open(_logo_png, "rb") as _f:
                _logo_b64 = _b64.b64encode(_f.read()).decode("utf-8")
            brand_content = (
                f'<img src="data:image/png;base64,{_logo_b64}"'
                f' alt="AtkinsRéalis" style="height:22px;display:block;">'
            )
        else:
            brand_content = (
                '<svg width="26" height="22" viewBox="0 0 26 22" xmlns="http://www.w3.org/2000/svg">'
                '<polygon points="13,1 25,21 1,21" fill="none" stroke="#e63329" stroke-width="2.2"/>'
                '<line x1="7.5" y1="14" x2="18.5" y2="14" stroke="#e63329" stroke-width="2.2"/>'
                '</svg>'
                '<span>AtkinsRéalis</span>'
            )
        brand_content_json = json.dumps(brand_content).replace("</", "<\\/")

        # Pre-build left panel HTML (map info + optional map views section)
        _left_panel_needed = _info_enabled or bool(self.map_views)
        if _left_panel_needed:
            _panel_title_html = _info_title if _info_enabled else "Map Views"
            _footer_parts = []
            _doc_block_html = ""
            if _info_enabled:
                if _info_date:
                    _footer_parts.append(f"<span>{_info_date}</span>")
                # Formal document title block
                _proj_rows = (
                    (f'<tr><th>Client</th><td>{_info_client}</td></tr>' if _info_client else "")
                    + (f'<tr><th>Project</th><td>{_info_project}</td></tr>' if _info_project else "")
                )
                _dc_rows = "".join(
                    f'<tr><th>{role}</th><td>{name}</td><td>{date}</td></tr>'
                    for role, name, date in _doc_control if name or date
                )
                if _proj_rows or _dc_rows:
                    _proj_tbl = f'<table class="doc-proj-table">{_proj_rows}</table>' if _proj_rows else ""
                    _dc_tbl = (
                        f'<table class="doc-ctrl-table"><thead><tr>'
                        f'<th>Role</th><th>Name</th><th>Date</th>'
                        f'</tr></thead><tbody>{_dc_rows}</tbody></table>'
                    ) if _dc_rows else ""
                    _doc_block_html = f'<div class="doc-block">{_proj_tbl}{_dc_tbl}</div>'
            _footer_html = (
                f'<div id="left-panel-footer">{"".join(_footer_parts)}</div>'
                if _footer_parts else ""
            )
            if _info_enabled:
                _body_html = (
                    f'<div id="left-panel-body">'
                    f'<div class="left-panel-desc">{_info_text or "&nbsp;"}</div>'
                    f'<div id="map-views-section"></div>'
                    f'{_doc_block_html}'
                    f'</div>'
                    f'{_footer_html}'
                )
            else:
                _body_html = (
                    f'<div id="left-panel-body">'
                    f'<div id="map-views-section"></div>'
                    f'</div>'
                )
            left_panel_html = (
                f'<div id="left-panel">'
                f'<div id="left-panel-hdr">'
                f'<span id="left-panel-title">{_panel_title_html}</span>'
                f'<button id="left-panel-close" title="Close">&#10005;</button>'
                f'</div>'
                f'{_body_html}'
                f'</div>'
            )
        else:
            left_panel_html = ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_page_title}</title>
{leaflet_head}
{plugin_heads}
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; font-family: sans-serif; overflow: hidden; }}
  body {{ display: flex; }}
  #left-panel {{
    width: 300px;
    flex-shrink: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #fff;
    border-right: 1px solid #ddd;
    box-shadow: 2px 0 6px rgba(0,0,0,0.1);
    z-index: 400;
    overflow: hidden;
  }}
  #map-wrap {{
    flex: 1;
    position: relative;
    overflow: hidden;
    min-height: 0;
  }}
  #map {{ position: absolute; inset: 0; }}

  /* ── Legend panel ─────────────────────────────────────────────── */
  #legend {{
    position: absolute;
    top: 10px; right: 10px;
    z-index: 1000;
    background: rgba(255,255,255,0.96);
    border: 1px solid #bbb;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    min-width: 180px;
    max-width: 260px;
    max-height: calc(100vh - 60px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  #legend-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 7px 10px 6px;
    background: #003057;
    border-bottom: 1px solid #002144;
    cursor: default;
    user-select: none;
    border-radius: 6px 6px 0 0;
  }}
  #legend-header span {{ font-weight: bold; font-size: 13px; color: #fff; }}
  #legend-toggle-all {{
    font-size: 11px;
    color: rgba(255,255,255,0.85);
    cursor: pointer;
    padding: 2px 5px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.35);
    background: rgba(255,255,255,0.12);
    line-height: 1.4;
  }}
  #legend-toggle-all:hover {{ background: rgba(255,255,255,0.25); }}
  #legend-body {{
    overflow-y: auto;
    padding: 4px 0;
  }}
  .legend-layer {{
    padding: 0;
  }}
  .legend-layer-row {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    cursor: pointer;
    user-select: none;
    transition: background 0.1s;
  }}
  .legend-layer-row:hover {{ background: #e8f0f7; }}
  .legend-layer-row input[type=checkbox] {{
    margin: 0;
    cursor: pointer;
    flex-shrink: 0;
  }}
  .legend-layer-name {{
    font-size: 12px;
    color: #222;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .legend-expand {{
    font-size: 10px;
    color: #888;
    flex-shrink: 0;
    transition: transform 0.2s;
  }}
  .legend-entries {{
    display: none;
    padding: 0 0 3px 26px;
  }}
  .legend-entries.open {{ display: block; }}
  .legend-entry {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px 2px 0;
  }}
  .legend-entry-label {{
    font-size: 11px;
    color: #444;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .legend-entry input[type=checkbox] {{
    margin: 0;
    cursor: pointer;
    flex-shrink: 0;
  }}
  .legend-entry.class-hidden .legend-entry-label,
  .legend-entry.class-hidden .legend-swatch {{ opacity: 0.35; }}
  .legend-swatch svg {{ display: block; }}
  .legend-layer.hidden .legend-layer-name {{ opacity: 0.45; }}
  .qgis-marker {{ background: none; border: none; }}

  /* ── Legend group styles ──────────────────────────────────────────── */
  .legend-group {{ }}
  .legend-group-hdr {{
    display: flex; align-items: center; gap: 5px;
    padding: 5px 10px 3px;
    cursor: pointer; user-select: none;
    border-top: 1px solid #eee;
  }}
  .legend-group-hdr input[type=checkbox] {{ margin: 0; cursor: pointer; flex-shrink: 0; }}
  .legend-group-hdr:hover {{ background: #e8f0f7; }}
  .legend-group-name {{ font-size: 12px; font-weight: 600; color: #003057; }}
  .legend-group-body {{ padding-left: 8px; }}
  .legend-group-body:not(.open) {{ display: none; }}

  /* ── Layer cog button ─────────────────────────────────────────── */
  .legend-cog-btn {{
    flex-shrink: 0;
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 3px;
    color: #aaa;
    border-radius: 3px;
    line-height: 1;
    display: flex;
    align-items: center;
  }}
  .legend-cog-btn:hover {{ color: #444; background: #e8e8e8; }}
  .legend-cog-btn.active {{ color: #003057; background: #d0e5f0; }}

  /* ── Per-layer settings panel ─────────────────────────────────── */
  .layer-settings {{
    display: none;
    padding: 4px 10px 6px 26px;
    border-top: 1px solid #eee;
    background: #fafafa;
  }}
  .layer-settings.open {{ display: block; }}
  .layer-settings-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
  }}
  .layer-settings-label {{ font-size: 11px; color: #555; min-width: 52px; flex-shrink: 0; }}
  .layer-settings-row input[type=range] {{ flex: 1; height: 14px; cursor: pointer; }}
  .layer-settings-row input[type=checkbox] {{ margin: 0; cursor: pointer; }}

  /* ── Feature labels ───────────────────────────────────────────── */
  .leaflet-tooltip.qgis-label {{
    background: none !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    pointer-events: none;
  }}
  .leaflet-tooltip.qgis-label::before {{ display: none !important; }}

  /* ── Filter toolbar ───────────────────────────────────────────── */
  #filterbar {{
    position: absolute;
    top: 10px; left: 50px;
    z-index: 1000;
    background: rgba(255,255,255,0.96);
    border: 1px solid #bbb;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    padding: 6px 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    max-width: calc(100vw - 320px);
    font-size: 12px;
  }}
  #filterbar label {{ font-weight: bold; color: #444; }}
  #filterbar select {{
    font-size: 12px;
    padding: 3px 4px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    max-width: 160px;
  }}
  #filterbar button {{
    font-size: 12px;
    padding: 3px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
  }}
  #filterbar button:hover {{ background: #e8f0f7; }}
  #filter-values-wrap {{ position: relative; }}
  #filter-values-btn {{
    min-width: 140px;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  #filter-values-panel {{
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 2px;
    background: #fff;
    border: 1px solid #bbb;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    min-width: 200px;
    max-width: 280px;
    z-index: 1100;
  }}
  #filter-values-panel.open {{ display: block; }}
  #filter-values-search {{
    width: 100%;
    box-sizing: border-box;
    border: none;
    border-bottom: 1px solid #ddd;
    padding: 6px 8px;
    font-size: 12px;
    outline: none;
  }}
  #filter-values-list {{
    max-height: 240px;
    overflow-y: auto;
    padding: 4px 0;
  }}
  .filter-value-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    cursor: pointer;
  }}
  .filter-value-item:hover {{ background: #f3f3f3; }}
  .filter-value-item span {{
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .filter-count {{ color: #888; font-size: 11px; }}

  /* ── Filter toggle button (Leaflet control) ───────────────────── */
  .leaflet-control-filter {{
    width: 30px; height: 30px;
    background: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }}
  .leaflet-control-filter:hover {{ background: #f4f4f4; }}
  .leaflet-control-filter.active {{
    background: #dde8ff;
  }}

  /* ── Brand watermark (Leaflet control at bottomleft) ─────────── */
  .brand-watermark {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 4px;
    padding: 4px 8px 4px 6px;
    pointer-events: none;
    user-select: none;
  }}
  .brand-watermark svg {{ display: block; flex-shrink: 0; max-height: 22px; }}
  .brand-watermark span {{
    font-family: Arial, sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: #003057;
    line-height: 1;
  }}

  /* ── Left info / scenes panel ─────────────────────────────────── */
  #left-panel-hdr {{
    background: #003057;
    padding: 12px 14px 10px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    flex-shrink: 0;
  }}
  #left-panel-title {{
    font-size: 15px;
    font-weight: bold;
    color: #fff;
    flex: 1;
    line-height: 1.3;
    margin: 0;
  }}
  #left-panel-close {{
    background: none;
    border: none;
    cursor: pointer;
    color: rgba(255,255,255,0.65);
    font-size: 16px;
    padding: 0;
    line-height: 1;
    flex-shrink: 0;
    margin-top: 1px;
  }}
  #left-panel-close:hover {{ color: #fff; }}
  #left-panel-body {{
    padding: 12px 14px;
    overflow-y: auto;
    flex: 1;
    font-size: 13px;
    color: #333;
    line-height: 1.55;
    white-space: pre-line;
  }}
  #left-panel-footer {{
    padding: 8px 14px;
    border-top: 1px solid #e5e5e5;
    font-size: 11px;
    color: #888;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  /* ── Formal document title block ─────────────────────────────────── */
  .doc-block {{
    margin-top: 14px;
    border-top: 2px solid #003057;
    padding-top: 10px;
  }}
  .doc-proj-table {{
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 8px;
    font-size: 11px;
  }}
  .doc-proj-table th {{
    text-align: left;
    width: 58px;
    color: #003057;
    font-weight: 700;
    padding: 2px 6px 2px 0;
    vertical-align: top;
  }}
  .doc-proj-table td {{ color: #222; padding: 2px 0; }}
  .doc-ctrl-table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 11px;
  }}
  .doc-ctrl-table th, .doc-ctrl-table td {{
    padding: 3px 6px;
    border: 1px solid #c0cad8;
    text-align: left;
  }}
  .doc-ctrl-table thead th {{
    background: #003057;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-color: #002144;
  }}
  .doc-ctrl-table tbody th {{
    background: #eef2f8;
    color: #003057;
    font-weight: 700;
    width: 70px;
    border-color: #c0cad8;
  }}
  .doc-ctrl-table tbody tr:nth-child(even) td {{ background: #f7f9fc; }}
  /* ── Label SVG overlay ───────────────────────────────────────────── */
  #label-overlay {{
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    pointer-events: none; z-index: 850; overflow: hidden;
  }}
  #map-views-section {{ flex-shrink: 0; }}
  .mv-item {{
    padding: 9px 14px 9px 12px;
    border-left: 3px solid transparent;
    cursor: pointer;
    border-bottom: 1px solid #eee;
    transition: background 0.12s;
  }}
  .mv-item:last-child {{ border-bottom: none; }}
  .mv-item:hover {{ background: #f0f4f8; border-left-color: #ccd8e4; }}
  .mv-item.active {{ background: #e8f0f7; border-left-color: #003057; }}
  .mv-item-name {{
    font-size: 12px; font-weight: 600; color: #003057; line-height: 1.3;
  }}
  .mv-item-notes {{ font-size: 11px; color: #666; margin-top: 2px; line-height: 1.35; }}
  .map-info-toggle {{
    width: 30px; height: 30px;
    background: white;
    border: none;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: bold; color: #444;
    padding: 0;
  }}
  .map-info-toggle:hover {{ background: #e8f0f7; color: #003057; }}

  /* ── Feature info panel */
  #info-panel {{
    display: none;
    position: absolute;
    left: 10px; bottom: 60px;
    z-index: 1001;
    background: rgba(255,255,255,0.97);
    border: 1px solid #bbb;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    min-width: 200px; max-width: 320px;
    max-height: calc(100vh - 180px);
    flex-direction: column;
    overflow: hidden;
  }}
  #info-panel.open {{ display: flex; }}
  #info-panel.split {{ min-width: 380px; max-width: 520px; }}
  #info-panel.split #info-panel-body {{ padding: 0; overflow: hidden; display: flex; flex: 1; min-height: 0; }}
  .info-split {{ display: flex; flex: 1; overflow: hidden; min-height: 0; }}
  .info-list-pane {{
    width: 150px; flex-shrink: 0; border-right: 1px solid #ddd;
    overflow-y: auto; background: #f7f9fb;
  }}
  .info-list-pane .mf-item {{
    border-bottom: 1px solid #eee; padding: 7px 8px; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 7px;
  }}
  .info-list-pane .mf-item .mf-swatch {{ flex-shrink: 0; line-height: 0; }}
  .info-list-pane .mf-item .mf-text {{ flex: 1; min-width: 0; }}
  .info-list-pane .mf-item:hover {{ background: #e8f0f7; }}
  .info-list-pane .mf-item.active {{ background: #003057; }}
  .info-list-pane .mf-item.active .mf-feature-name {{ color: #fff; }}
  .info-list-pane .mf-item.active .mf-layer-name {{ color: rgba(255,255,255,0.65); }}
  .info-list-pane .mf-item.active .mf-swatch svg {{ opacity: 0.85; }}
  .info-detail-pane {{
    flex: 1; overflow-y: auto; padding: 8px 12px;
    font-size: 12px; color: #666; min-width: 0;
  }}
  .info-detail-pane table {{ border-collapse: collapse; width: 100%; }}
  .info-detail-pane th {{
    text-align: left; padding: 2px 8px 2px 0;
    color: #555; font-weight: 600; white-space: nowrap; vertical-align: top;
  }}
  .info-detail-pane td {{ padding: 2px 0; word-break: break-word; color: #222; }}
  #info-panel-hdr {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 10px 6px; background: #003057;
    border-bottom: 1px solid #002144; border-radius: 6px 6px 0 0;
    user-select: none;
  }}
  #info-panel-hdr span {{ font-weight: bold; font-size: 13px; color: #fff; }}
  #info-panel-close {{
    background: none; border: none; cursor: pointer;
    font-size: 14px; color: rgba(255,255,255,0.65); padding: 0 2px; line-height: 1;
  }}
  #info-panel-close:hover {{ color: #fff; }}
  #info-panel-body {{
    padding: 8px 12px; overflow-y: auto; flex: 1;
    font-size: 12px; color: #666;
  }}
  #info-panel-body table {{ border-collapse: collapse; width: 100%; }}
  #info-panel-body th {{
    text-align: left; padding: 2px 8px 2px 0;
    color: #555; font-weight: 600; white-space: nowrap; vertical-align: top;
  }}
  #info-panel-body td {{ padding: 2px 0; word-break: break-word; color: #222; }}
  .mf-list {{ padding: 4px 0; }}
  .mf-item {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0;
  }}
  .mf-item:hover {{ background: #e8f0f7; }}
  .mf-feature-name {{ font-size: 12px; color: #222; font-weight: 600; }}
  .mf-layer-name {{ font-size: 10px; color: #888; margin-top: 1px; }}
  .mf-layer {{ font-size: 12px; color: #333; }}
  .mf-arrow {{ color: #aaa; font-size: 16px; flex-shrink: 0; }}
  /* ── Drag-select rubber-band rectangle */
  #select-rect {{
    position: absolute; pointer-events: none; display: none;
    border: 2px dashed #3388ff; background: rgba(51,136,255,0.08); z-index: 999;
  }}
  /* ── Drag-select toolbar button active state */
  .select-btn-active {{ background: #003057 !important; color: #fff !important; }}
  /* ── Attr table selection badge */
  #attr-select-badge {{
    display: none; font-size: 11px; padding: 2px 7px;
    background: #003057; color: #fff; border-radius: 10px; white-space: nowrap;
  }}
  #attr-select-clear {{
    display: none; font-size: 11px; padding: 2px 7px; cursor: pointer;
    border: 1px solid #ccc; border-radius: 3px; background: #fff;
  }}
  #attr-select-clear:hover {{ background: #eee; }}
  .mf-back {{
    display: block; width: 100%; background: #e8f0f7; border: none;
    border-bottom: 1px solid #d0dde8; padding: 5px 12px; text-align: left;
    cursor: pointer; font-size: 11px; color: #003057; margin-bottom: 4px;
  }}
  .mf-back:hover {{ background: #d0e5f0; }}

  /* ── Attribute table panel */
  #attr-table-panel {{
    display: none;
    position: absolute;
    left: 0; right: 0; bottom: 0;
    height: 240px;
    z-index: 1002;
    background: #fff;
    border-top: 2px solid #003057;
    flex-direction: column;
    overflow: hidden;
  }}
  #attr-table-panel.open {{ display: flex; }}
  #attr-table-hdr {{
    display: flex; align-items: center; gap: 8px;
    padding: 5px 10px;
    background: #003057; border-bottom: 1px solid #002144;
    flex-shrink: 0;
  }}
  #attr-table-hdr span {{ font-weight: bold; font-size: 13px; color: #fff; }}
  #attr-table-layer {{ font-size: 12px; padding: 2px 4px; border: 1px solid rgba(255,255,255,0.3); border-radius: 3px; background: rgba(255,255,255,0.12); color: #fff; }}
  #attr-table-close {{
    margin-left: auto; background: none; border: none;
    cursor: pointer; font-size: 14px; color: rgba(255,255,255,0.65); padding: 0 4px;
  }}
  #attr-table-close:hover {{ color: #fff; }}
  #attr-table-body {{
    overflow: auto; flex: 1;
  }}
  #attr-table-body table {{
    border-collapse: collapse; width: 100%; font-size: 12px;
  }}
  #attr-table-body th {{
    position: sticky; top: 0;
    background: #e8f0f7; border-bottom: 2px solid #003057;
    padding: 4px 8px; text-align: left;
    cursor: pointer; user-select: none; white-space: nowrap; color: #003057;
  }}
  #attr-table-body th:hover {{ background: #d0e5f0; }}
  #attr-table-body th.sort-asc::after  {{ content: ' ▲'; font-size: 9px; }}
  #attr-table-body th.sort-desc::after {{ content: ' ▼'; font-size: 9px; }}
  #attr-table-body td {{
    padding: 3px 8px; border-bottom: 1px solid #eee;
    white-space: nowrap; max-width: 200px;
    overflow: hidden; text-overflow: ellipsis;
  }}
  #attr-table-body tr:hover td {{ background: #e8f0f7; cursor: pointer; }}
  #attr-table-body tr.selected td {{ background: #c0d9ec; }}

  /* ── Attribute table search & export ─────────────────────────── */
  #attr-table-search {{
    font-size: 12px;
    padding: 2px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    width: 130px;
    flex-shrink: 0;
    outline: none;
  }}
  #attr-table-csv {{
    font-size: 11px;
    padding: 2px 7px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
    flex-shrink: 0;
    white-space: nowrap;
  }}
  #attr-table-csv:hover {{ background: #eee; }}


</style>
</head>
<body>
{left_panel_html}
<div id="map-wrap">
<div id="map"></div>
<div id="select-rect"></div>
<div id="label-overlay"><svg id="label-svg" style="position:absolute;top:0;left:0;width:100%;height:100%;overflow:visible;"></svg></div>
<div id="filterbar" style="display:none">
  <label>Filter</label>
  <select id="filter-layer" title="Layer"></select>
  <select id="filter-attr" title="Attribute"></select>
  <span id="filter-values-wrap">
    <button id="filter-values-btn" type="button">All values</button>
    <div id="filter-values-panel">
      <input id="filter-values-search" type="text" placeholder="Type to search / filter…" autocomplete="off">
      <div id="filter-values-list"></div>
    </div>
  </span>
  <button id="filter-clear" type="button">Clear</button>
  <span id="filter-count" class="filter-count"></span>
</div>
<div id="legend" style="display:none"></div>
<div id="info-panel">
  <div id="info-panel-hdr">
    <span>Feature Info</span>
    <button id="info-panel-close" title="Close">&#10005;</button>
  </div>
  <div id="info-panel-body">Click a map feature to see its attributes.</div>
</div>
<div id="attr-table-panel">
  <div id="attr-table-hdr">
    <span>Attribute Table</span>
    <select id="attr-table-layer"></select>
    <span id="attr-select-badge"></span>
    <button id="attr-select-clear" title="Clear selection">&#10005; Clear</button>
    <input id="attr-table-search" type="text" placeholder="Search…" autocomplete="off">
    <button id="attr-table-csv" title="Export CSV">&#8595; CSV</button>
    <button id="attr-table-close" title="Close">&#10005;</button>
  </div>
  <div id="attr-table-body"></div>
</div>
</div>
<script>
(function() {{
  "use strict";

  var map = L.map('map', {{
    center: [0, 0], zoom: 2,
    maxZoom: 23,
    preferCanvas: true,
    contextmenu: true,
    contextmenuWidth: 180,
    contextmenuItems: [
      {{text: 'Centre map here',  callback: function(e) {{ map.panTo(e.latlng); }}}},
      {{text: 'Zoom in',          callback: function(e) {{ map.zoomIn(); }}}},
      {{text: 'Zoom out',         callback: function(e) {{ map.zoomOut(); }}}},
      '-',
      {{text: 'Copy lat, lon',    callback: function(e) {{
        var t = e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6);
        try {{ navigator.clipboard.writeText(t); }} catch(x) {{}}
      }}}},
      {{text: 'Fit to all data',  callback: function() {{
        try {{ map.fitBounds(bounds, {{padding:[20,20]}}); }} catch(x) {{}}
      }}}}
    ]
  }});
  var bounds = {bounds_json};
  try {{ map.fitBounds({initial_bounds_json}, {{padding: [20, 20]}}); }}
  catch(e) {{ map.setView([0, 0], 2); }}
  setTimeout(function() {{ map.invalidateSize(); }}, 50);

  // ── Left panel close & toggle ─────────────────────────────────────────────
  // Registered immediately after map init so it works even if later sections fail.
  (function() {{
    var panel = document.getElementById('left-panel');
    if (!panel) return;
    var closeBtn = document.getElementById('left-panel-close');
    if (closeBtn) {{
      closeBtn.addEventListener('click', function() {{
        panel.style.display = 'none';
        map.invalidateSize();
      }});
    }}
    var InfoToggle = L.Control.extend({{
      onAdd: function() {{
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control map-info-toggle');
        btn.type = 'button';
        btn.title = 'About this map';
        btn.innerHTML = 'ⓘ';
        L.DomEvent.on(btn, 'click', function(e) {{
          L.DomEvent.stopPropagation(e);
          var hidden = panel.style.display === 'none';
          panel.style.display = hidden ? 'flex' : 'none';
          map.invalidateSize();
        }});
        return btn;
      }}
    }});
    new InfoToggle({{position: 'topleft'}}).addTo(map);
  }})();

  var LAYERS = {layers_json};
  var INCLUDE_LEGEND = {include_legend};
  var LAYER_TREE = {tree_json};
  var THEMES = {themes_json};

  // ── Basemap (optional) ───────────────────────────────────────────────────
  var INCLUDE_BASEMAP = {include_basemap_json};
  var basemap = null;
  if (INCLUDE_BASEMAP) {{
    basemap = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxNativeZoom: 19,
      maxZoom: 23
    }}).addTo(map);
  }}

  // ── Scale bar (built-in) ──────────────────────────────────────────────────
  L.control.scale({{position: 'bottomleft', imperial: true, metric: true}}).addTo(map);

  // ── Fullscreen ────────────────────────────────────────────────────────────
  try {{
    if (typeof L.Control.Fullscreen !== 'undefined') {{
      new L.Control.Fullscreen({{
        position: 'topleft',
        title: {{false: 'Enter fullscreen', true: 'Exit fullscreen'}}
      }}).addTo(map);
    }}
  }} catch(e) {{ console.warn('Fullscreen plugin error:', e); }}

  // ── Mini-map overview (always shown as geographic context) ──────────────
  try {{
    if (typeof L.Control.MiniMap !== 'undefined') {{
      var miniTile = L.tileLayer(
        'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 19}});
      new L.Control.MiniMap(miniTile, {{
        position: 'bottomright', toggleDisplay: true, minimized: true,
        width: 160, height: 160
      }}).addTo(map);
    }}
  }} catch(e) {{ console.warn('MiniMap plugin error:', e); }}


  // ── Helpers ──────────────────────────────────────────────────────────────
  function escHtml(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}

  // Return the inner SVG element(s) for a marker shape centred at (cx, cy)
  // with circumradius r. Used by both map markers and legend swatches.
  function shapeSvgInner(shape, cx, cy, r, fill, fillOp, stroke, strokeW, strokeOp) {{
    if (strokeOp == null) strokeOp = 1;
    var attrs = ' fill="' + escHtml(fill) + '" fill-opacity="' + fillOp + '"'
              + ' stroke="' + escHtml(stroke) + '" stroke-width="' + strokeW + '"'
              + ' stroke-opacity="' + strokeOp + '"';
    function poly(pts) {{
      return '<polygon points="' + pts.map(function(p) {{ return p[0] + ',' + p[1]; }}).join(' ') + '"' + attrs + '/>';
    }}
    function regular(n, rot) {{
      var pts = [];
      for (var i = 0; i < n; i++) {{
        var a = rot + i * 2 * Math.PI / n;
        pts.push([(cx + r * Math.sin(a)).toFixed(2), (cy - r * Math.cos(a)).toFixed(2)]);
      }}
      return poly(pts);
    }}
    function starPts(points, outer, inner, rot) {{
      var pts = [];
      for (var i = 0; i < points * 2; i++) {{
        var rad = (i % 2 === 0) ? outer : inner;
        var a = rot + i * Math.PI / points;
        pts.push([(cx + rad * Math.sin(a)).toFixed(2), (cy - rad * Math.cos(a)).toFixed(2)]);
      }}
      return poly(pts);
    }}
    switch (shape) {{
      case 'square':
        return '<rect x="' + (cx - r) + '" y="' + (cy - r) + '" width="' + (2 * r) + '" height="' + (2 * r) + '"' + attrs + '/>';
      case 'diamond':
        return poly([[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]]);
      case 'triangle':
        return regular(3, 0);
      case 'pentagon':
        return regular(5, 0);
      case 'hexagon':
        return regular(6, 0);
      case 'octagon':
        return regular(8, Math.PI / 8);
      case 'star':
        return starPts(5, r, r * 0.5, 0);
      case 'cross':
        return '<path d="M' + cx + ' ' + (cy - r) + ' V' + (cy + r) + ' M' + (cx - r) + ' ' + cy + ' H' + (cx + r) + '"'
             + ' stroke="' + escHtml(stroke !== 'none' ? stroke : fill) + '" stroke-width="' + Math.max(1.5, strokeW * 2) + '" fill="none"/>';
      case 'x':
        return '<path d="M' + (cx - r) + ' ' + (cy - r) + ' L' + (cx + r) + ' ' + (cy + r)
             + ' M' + (cx + r) + ' ' + (cy - r) + ' L' + (cx - r) + ' ' + (cy + r) + '"'
             + ' stroke="' + escHtml(stroke !== 'none' ? stroke : fill) + '" stroke-width="' + Math.max(1.5, strokeW * 2) + '" fill="none"/>';
      default: // circle
        return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"' + attrs + '/>';
    }}
  }}

  function makeMarker(latlng, style, paneName) {{
    var size = style.markerSize || 8;
    var shape = style.markerShape || 'circle';
    var fill = style.markerColor || '#3388ff';
    var fillOp = style.markerOpacity != null ? style.markerOpacity : 0.9;
    var stroke = style.markerStrokeColor || '#555555';
    var strokeW = style.markerStrokeWidth != null ? style.markerStrokeWidth : 1;
    var strokeOp = (style.markerStrokeOpacity != null) ? style.markerStrokeOpacity : 1;
    if (shape === 'circle') {{
      var copts = {{
        radius: size / 2,
        fillColor: fill, fillOpacity: fillOp,
        color: stroke, weight: strokeW, opacity: strokeOp
      }};
      if (paneName) copts.pane = paneName;
      return L.circleMarker(latlng, copts);
    }}
    var pad = Math.max(strokeW, 1) + 2;
    var box = size + pad * 2;
    var c = box / 2, r = size / 2;
    var inner = shapeSvgInner(shape, c, c, r, fill, fillOp, stroke, strokeW, strokeOp);
    var angle = style.markerAngle || 0;
    var rot = angle ? ' transform="rotate(' + angle + ' ' + c + ' ' + c + ')"' : '';
    var svg = '<svg width="' + box + '" height="' + box
            + '" xmlns="http://www.w3.org/2000/svg" style="overflow:visible">'
            + '<g' + rot + '>' + inner + '</g></svg>';
    var icon = L.divIcon({{ html: svg, className: 'qgis-marker',
                            iconSize: [box, box], iconAnchor: [c, c] }});
    var mopts = {{ icon: icon }};
    if (paneName) mopts.pane = paneName;
    return L.marker(latlng, mopts);
  }}

  function resolveStyle(styleMap, props) {{
    var t = styleMap.type;
    if (t === 'single') return styleMap.style;
    if (t === 'categorized') {{
      var propVal = props[styleMap.field];
      var val = (propVal == null) ? null : String(propVal);
      for (var i = 0; i < styleMap.entries.length; i++) {{
        var ev = styleMap.entries[i].value;
        var entVal = (ev == null) ? null : String(ev);
        if (entVal === val) return styleMap.entries[i].style;
      }}
      return styleMap.default || {{}};
    }}
    if (t === 'graduated') {{
      var v = parseFloat(props[styleMap.field]);
      for (var i = 0; i < styleMap.entries.length; i++) {{
        var e = styleMap.entries[i];
        if (v >= e.min && v <= e.max) return e.style;
      }}
      return styleMap.default || {{}};
    }}
    if (t === 'rule') {{
      return (styleMap.entries[0] && styleMap.entries[0].style) || styleMap.default || {{}};
    }}
    return {{}};
  }}

  function resolveEntryIndex(styleMap, props) {{
    var t = styleMap.type;
    if (t === 'categorized') {{
      var propVal = props[styleMap.field];
      var val = (propVal == null) ? null : String(propVal);
      for (var i = 0; i < styleMap.entries.length; i++) {{
        var ev = styleMap.entries[i].value;
        var entVal = (ev == null) ? null : String(ev);
        if (entVal === val) return i;
      }}
      return -1;
    }}
    if (t === 'graduated') {{
      var v = parseFloat(props[styleMap.field]);
      for (var i = 0; i < styleMap.entries.length; i++) {{
        var e = styleMap.entries[i];
        if (v >= e.min && v <= e.max) return i;
      }}
      return -1;
    }}
    return -1;
  }}

  function leafletPathStyle(s) {{
    return {{
      color: s.color || '#3388ff',
      weight: s.weight != null ? s.weight : 2,
      opacity: s.opacity != null ? s.opacity : 1,
      fillColor: s.fillColor || s.color || '#3388ff',
      fillOpacity: s.fillOpacity != null ? s.fillOpacity : 0.4
    }};
  }}

  // ── Swatch SVG ───────────────────────────────────────────────────────────
  function swatchSvg(geomType, style) {{
    var W = 20, H = 16;
    var svg = '<svg width="' + W + '" height="' + H + '" xmlns="http://www.w3.org/2000/svg">';
    if (geomType === 'point') {{
      var r = Math.min(6, Math.max(3, (style.markerSize || 8) / 2));
      var cx = W / 2, cy = H / 2;
      svg += shapeSvgInner(
        style.markerShape || 'circle', cx, cy, r,
        style.markerColor || '#3388ff',
        style.markerOpacity != null ? style.markerOpacity : 0.9,
        style.markerStrokeColor || '#666',
        Math.min(1.5, style.markerStrokeWidth != null ? style.markerStrokeWidth : 1),
        style.markerStrokeOpacity != null ? style.markerStrokeOpacity : 1
      );
    }} else if (geomType === 'line') {{
      var w = Math.min(5, Math.max(1, style.weight || 2));
      svg += '<line x1="1" y1="' + (H/2) + '" x2="' + (W-1) + '" y2="' + (H/2) + '"'
          + ' stroke="' + escHtml(style.color || '#3388ff') + '"'
          + ' stroke-opacity="' + (style.opacity != null ? style.opacity : 1) + '"'
          + ' stroke-width="' + w + '"/>';
    }} else if (geomType === 'raster') {{
      svg += '<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="4" height="4">'
          + '<path d="M0,4 L4,0" stroke="#777" stroke-width="1"/></pattern></defs>'
          + '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
          + ' fill="url(#hatch)" stroke="#999" stroke-width="1"/>';
    }} else {{
      svg += '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
          + ' fill="' + escHtml(style.fillColor || '#3388ff') + '"'
          + ' fill-opacity="' + (style.fillOpacity != null ? style.fillOpacity : 0.4) + '"'
          + ' stroke="' + escHtml(style.color || '#333') + '"'
          + ' stroke-opacity="' + (style.opacity != null ? style.opacity : 1) + '"'
          + ' stroke-width="' + Math.min(3, style.weight || 1) + '"/>';
    }}
    return svg + '</svg>';
  }}

  // ── Layer builder ────────────────────────────────────────────────────────
  function buildVectorLayer(item) {{
    var ld = item.ld;
    var opts = {{
      pane: item.paneName,
      onEachFeature: onEachFeature,
      filter: function(feature) {{
        if (item.filterFn && !item.filterFn(feature)) return false;
        if (item.hiddenClasses && item.hiddenClasses.length) {{
          var idx = resolveEntryIndex(item.ld.styleMap, feature.properties || {{}});
          if (item.hiddenClasses.indexOf(idx) !== -1) return false;
        }}
        return true;
      }}
    }};
    if (ld.geomType === 'point') {{
      opts.pointToLayer = function(feature, latlng) {{
        return makeMarker(latlng, resolveStyle(ld.styleMap, feature.properties || {{}}), item.paneName);
      }};
    }} else {{
      opts.style = function(feature) {{
        return leafletPathStyle(resolveStyle(ld.styleMap, feature.properties || {{}}));
      }};
    }}
    var geoLayer = L.geoJSON(ld.geojson, opts);
    if (item.clusterEnabled && ld.geomType === 'point' && typeof L.markerClusterGroup !== 'undefined') {{
      var cg = L.markerClusterGroup({{
        chunkedLoading: true,
        maxClusterRadius: 80,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true
      }});
      cg.addLayer(geoLayer);
      return cg;
    }}
    return geoLayer;
  }}

  function buildRasterLayer(item) {{
    return L.imageOverlay('data:image/png;base64,' + item.ld.data, item.ld.bounds, {{
      opacity: 1, pane: item.paneName
    }});
  }}

  function buildWmsLayer(item) {{
    var ld = item.ld;
    // XYZ and WMTS tile services use a URL template — serve directly as tile layer
    if (ld.tileType === 'xyz' || ld.tileType === 'wmts') {{
      return L.tileLayer(ld.wmsUrl, {{ pane: item.paneName, maxZoom: 23 }});
    }}
    return L.tileLayer.wms(ld.wmsUrl, {{
      layers:      ld.wmsLayers,
      format:      ld.wmsFormat  || 'image/png',
      styles:      ld.wmsStyles  || '',
      version:     ld.wmsVersion || '1.1.1',
      transparent: true,
      opacity:     1,
      pane:        item.paneName,
      maxZoom:     23
    }});
  }}

  function buildLayer(item) {{
    if (item.ld.kind === 'vector') return buildVectorLayer(item);
    if (item.ld.kind === 'wms')    return buildWmsLayer(item);
    return buildRasterLayer(item);
  }}

  // Rebuild a layer in place (used after a filter change), preserving visibility.
  function rebuildLayer(item) {{
    var wasVisible = item.visible;
    if (item.lfl) map.removeLayer(item.lfl);
    item.lfl = buildLayer(item);
    if (wasVisible) item.lfl.addTo(map);
    if (item.ld.labelConfig) {{
      buildLabels(item);
      setLayerLabels(item, item.labelsVisible);
    }}
  }}

  function onEachFeature(feature, layer) {{
    if (!feature.properties) return;
    var rows = Object.entries(feature.properties)
      .filter(function(e) {{ return e[1] != null; }})
      .map(function(e) {{
        return '<tr><th>'+escHtml(e[0])+'</th><td>'+escHtml(String(e[1]))+'</td></tr>';
      }}).join('');
    if (rows) {{
      layer._infoHtml = '<table>'+rows+'</table>';
      layer._feature = feature;
    }}
  }}

  // Build Leaflet layers and collect metadata for legend.
  // Each layer gets a dedicated map pane so its opacity can be controlled
  // uniformly (works for vector markers, paths, rasters and WMS alike).
  var legendItems = [];
  var _allLabelItems = [];
  var _labelPlacementMode = 'candidate';
  var _labelSvg = document.getElementById('label-svg');
  for (var i = 0; i < LAYERS.length; i++) {{
    var paneName = 'layerPane' + i;
    map.createPane(paneName);
    map.getPane(paneName).style.zIndex = 400 + i;

    var labelPaneName = 'labelPane' + i;
    map.createPane(labelPaneName);
    map.getPane(labelPaneName).style.zIndex = 650 + i;
    map.getPane(labelPaneName).style.pointerEvents = 'none';

    var item = {{
      ld: LAYERS[i], paneName: paneName, labelPaneName: labelPaneName,
      visible: true, labelsVisible: false, filterFn: null, lfl: null, index: i,
      clusterEnabled: false, hiddenClasses: []
    }};
    try {{
      item.lfl = buildLayer(item);
      item.lfl.addTo(map);
      if (item.ld.labelConfig) {{
        buildLabels(item);
        if (item.ld.labelConfig.enabled) setLayerLabels(item, true);
      }}
      legendItems.push(item);
    }} catch(layerErr) {{
      console.error('Layer render failed:', LAYERS[i] && LAYERS[i].name, layerErr);
    }}
  }}

  // ── Feature info panel ───────────────────────────────────────────────────
  var infoPanel = document.getElementById('info-panel');
  var infoPanelBody = document.getElementById('info-panel-body');
  document.getElementById('info-panel-close').addEventListener('click', function() {{
    infoPanel.classList.remove('open');
    infoPanel.classList.remove('split');
  }});
  var InfoBtn = L.Control.extend({{
    onAdd: function() {{
      var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
      btn.title = 'Feature info';
      btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;font-size:16px;cursor:pointer;background:white;border-radius:4px;';
      btn.innerHTML = '&#9432;';
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', function() {{ infoPanel.classList.toggle('open'); }});
      return btn;
    }}
  }});
  new InfoBtn({{position: 'topleft'}}).addTo(map);

  // ── Attribute table button ────────────────────────────────────────────────
  var AttrTableBtn = L.Control.extend({{
    onAdd: function() {{
      var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
      btn.title = 'Attribute table';
      btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;font-size:14px;cursor:pointer;background:white;border-radius:4px;';
      btn.innerHTML = '&#8801;';
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', function() {{
        var panel = document.getElementById('attr-table-panel');
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) populateAttrTable();
      }});
      return btn;
    }}
  }});
  new AttrTableBtn({{position: 'topleft'}}).addTo(map);

  // ── Drag-select button ────────────────────────────────────────────────────
  var _selectMode = false;
  var SelectBtn = L.Control.extend({{
    onAdd: function() {{
      var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
      btn.title = 'Drag to select features';
      btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;font-size:16px;cursor:pointer;background:white;border-radius:4px;';
      btn.innerHTML = '&#x2B1A;';
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', function() {{
        _selectMode = !_selectMode;
        btn.classList.toggle('select-btn-active', _selectMode);
        map.getContainer().style.cursor = _selectMode ? 'crosshair' : '';
        if (!_selectMode) selectRect.style.display = 'none';
      }});
      return btn;
    }}
  }});
  new SelectBtn({{position: 'topleft'}}).addTo(map);

  var attrTablePanel = document.getElementById('attr-table-panel');
  var attrTableLayer = document.getElementById('attr-table-layer');
  var attrTableBody  = document.getElementById('attr-table-body');
  var attrTableSearch = document.getElementById('attr-table-search');
  var _attrSelectSet = null;

  var _highlightLayer = null;
  function highlightFeatureOnMap(feat) {{
    if (_highlightLayer) {{ map.removeLayer(_highlightLayer); _highlightLayer = null; }}
    if (!feat || !feat.geometry) return;
    try {{
      _highlightLayer = L.geoJSON(feat, {{
        style: {{ color: '#ffcc00', weight: 4, opacity: 1, fillColor: '#ffff00', fillOpacity: 0.3 }},
        pointToLayer: function(f, latlng) {{
          return L.circleMarker(latlng, {{ radius: 12, color: '#ffcc00', weight: 3, fillColor: '#ffff00', fillOpacity: 0.5 }});
        }}
      }}).addTo(map);
    }} catch(e) {{}}
  }}

  document.getElementById('attr-table-close').addEventListener('click', function() {{
    attrTablePanel.classList.remove('open');
    if (_highlightLayer) {{ map.removeLayer(_highlightLayer); _highlightLayer = null; }}
  }});

  document.getElementById('attr-select-clear').addEventListener('click', function() {{
    _attrSelectSet = null;
    populateAttrTable();
  }});

  document.getElementById('attr-table-csv').addEventListener('click', function() {{
    var idx = parseInt(attrTableLayer.value, 10);
    var item = legendItems[idx];
    if (!item || item.ld.kind !== 'vector') return;
    var feats = item.ld.geojson.features;
    if (!feats || !feats.length) return;
    var cols = [], seen = {{}};
    for (var i = 0; i < feats.length; i++) {{
      var p = feats[i].properties || {{}};
      Object.keys(p).forEach(function(k) {{ if (!(k in seen)) {{ seen[k]=1; cols.push(k); }} }});
    }}
    var lines = [cols.map(function(c) {{ return '"' + c.replace(/"/g,'""') + '"'; }}).join(',')];
    feats.forEach(function(f) {{
      var p = f.properties || {{}};
      lines.push(cols.map(function(c) {{
        var v = p[c]; if (v == null) return '';
        return '"' + String(v).replace(/"/g,'""') + '"';
      }}).join(','));
    }});
    var blob = new Blob([lines.join('\\n')], {{type:'text/csv'}});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = (item.ld.name || 'attributes') + '.csv';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }});

  function filterAttrTable() {{
    var q = attrTableSearch ? attrTableSearch.value.trim().toLowerCase() : '';
    attrTableBody.querySelectorAll('tr[data-fi]').forEach(function(tr) {{
      tr.style.display = (!q || tr.textContent.toLowerCase().indexOf(q) !== -1) ? '' : 'none';
    }});
  }}
  if (attrTableSearch) attrTableSearch.addEventListener('input', filterAttrTable);

  var _attrSortCol = null, _attrSortAsc = true;

  function populateAttrTable() {{
    var idx = parseInt(attrTableLayer.value, 10);
    var item = legendItems[idx];
    if (!item || item.ld.kind !== 'vector') return;
    var feats = item.ld.geojson.features;
    if (!feats || !feats.length) {{ attrTableBody.innerHTML = '<p style="padding:8px;color:#888">No features.</p>'; return; }}

    // Apply drag-select filter: build {{fi, f}} pairs preserving original indices
    var pairs = feats.map(function(f, fi) {{ return {{fi: fi, f: f}}; }});
    if (_attrSelectSet !== null) pairs = pairs.filter(function(p) {{ return _attrSelectSet.indexOf(p.fi) !== -1; }});

    // Update selection badge
    var badge = document.getElementById('attr-select-badge');
    var clearBtn = document.getElementById('attr-select-clear');
    if (badge) {{ badge.textContent = _attrSelectSet !== null ? pairs.length + ' selected' : ''; badge.style.display = _attrSelectSet !== null ? '' : 'none'; }}
    if (clearBtn) clearBtn.style.display = _attrSelectSet !== null ? '' : 'none';

    // Collect columns from first 100 filtered features
    var cols = [], seen = {{}};
    for (var i = 0; i < Math.min(pairs.length, 100); i++) {{
      var p = pairs[i].f.properties || {{}};
      Object.keys(p).forEach(function(k) {{ if (!(k in seen)) {{ seen[k]=1; cols.push(k); }} }});
    }}

    // Sort pairs preserving original feature index
    var sorted = pairs.slice();
    if (_attrSortCol !== null && cols.indexOf(_attrSortCol) !== -1) {{
      sorted.sort(function(a, b) {{
        var va = (a.f.properties || {{}})[_attrSortCol], vb = (b.f.properties || {{}})[_attrSortCol];
        var na = parseFloat(va), nb = parseFloat(vb);
        var cmp = (!isNaN(na) && !isNaN(nb)) ? (na-nb) : (String(va) < String(vb) ? -1 : String(va) > String(vb) ? 1 : 0);
        return _attrSortAsc ? cmp : -cmp;
      }});
    }}

    var html = '<table><thead><tr>';
    cols.forEach(function(c) {{
      var cls = (_attrSortCol === c) ? ('sort-' + (_attrSortAsc?'asc':'desc')) : '';
      html += '<th class="'+cls+'" data-col="'+escHtml(c)+'">'+escHtml(c)+'</th>';
    }});
    html += '</tr></thead><tbody>';
    sorted.forEach(function(pair) {{
      var p = pair.f.properties || {{}};
      html += '<tr data-fi="'+pair.fi+'">';
      cols.forEach(function(c) {{
        var v = p[c]; html += '<td title="'+(v!=null?escHtml(String(v)):'')+'">'+escHtml(v!=null?String(v):'')+'</td>';
      }});
      html += '</tr>';
    }});
    html += '</tbody></table>';
    attrTableBody.innerHTML = html;

    // Sort on header click
    attrTableBody.querySelectorAll('th').forEach(function(th) {{
      th.addEventListener('click', function() {{
        var col = th.getAttribute('data-col');
        if (_attrSortCol === col) {{ _attrSortAsc = !_attrSortAsc; }}
        else {{ _attrSortCol = col; _attrSortAsc = true; }}
        populateAttrTable();
      }});
    }});

    // Click row → show in info panel + highlight on map
    attrTableBody.querySelectorAll('tr[data-fi]').forEach(function(tr) {{
      tr.addEventListener('click', function() {{
        attrTableBody.querySelectorAll('tr.selected').forEach(function(r){{ r.classList.remove('selected'); }});
        tr.classList.add('selected');
        var fi = parseInt(tr.getAttribute('data-fi'), 10);
        var feat = feats[fi];
        if (!feat) return;
        if (feat.properties) {{
          var rws = Object.entries(feat.properties)
            .filter(function(e){{ return e[1]!=null; }})
            .map(function(e){{ return '<tr><th>'+escHtml(e[0])+'</th><td>'+escHtml(String(e[1]))+'</td></tr>'; }}).join('');
          infoPanelBody.innerHTML = '<table>'+rws+'</table>';
          infoPanel.classList.add('open');
        }}
        highlightFeatureOnMap(feat);
        if (feat.geometry) {{
          try {{
            var geo = L.geoJSON(feat);
            var b = geo.getBounds();
            if (b.isValid()) map.fitBounds(b, {{maxZoom: 16, padding: [40,40]}});
          }} catch(e) {{}}
        }}
      }});
    }});
    filterAttrTable();
  }}

  // ── Legend panel ─────────────────────────────────────────────────────────
  try {{ if (INCLUDE_LEGEND && legendItems.length > 0) {{
    var panel = document.getElementById('legend');
    panel.style.display = 'flex';

    // Header
    var hdr = document.getElementById('legend-header') || document.createElement('div');
    hdr.id = 'legend-header';
    hdr.innerHTML = '<span>Layers</span><button id="legend-toggle-all">Hide all</button>';
    panel.appendChild(hdr);

    var body = document.createElement('div');
    body.id = 'legend-body';
    panel.appendChild(body);

    var allVisible = true;
    document.getElementById('legend-toggle-all').addEventListener('click', function() {{
      allVisible = !allVisible;
      this.textContent = allVisible ? 'Hide all' : 'Show all';
      legendItems.forEach(function(item) {{
        setLayerVisible(item, allVisible);
      }});
    }});

    // Legend items are shown top-to-bottom (reverse of draw order)
    var displayItems = legendItems.slice().reverse();

    var COG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
      + '<path d="M12 15.5a3.5 3.5 0 0 1-3.5-3.5 3.5 3.5 0 0 1 3.5-3.5 3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5m7.43-2.92c.04-.32.07-.64.07-.97s-.03-.66-.07-1l2.16-1.68c.19-.15.24-.42.12-.64l-2.04-3.53c-.12-.22-.39-.3-.61-.22l-2.55 1.03c-.52-.4-1.08-.73-1.69-.98l-.38-2.72C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.72c-.61.25-1.17.59-1.69.98l-2.55-1.03c-.22-.08-.49 0-.61.22L2.74 8.87c-.13.22-.07.49.12.64L5.02 11.19c-.04.34-.07.67-.07 1s.03.65.07.97L2.86 14.84c-.19.15-.24.42-.12.64l2.04 3.53c.12.22.39.3.61.22l2.55-1.03c.52.4 1.08.73 1.69.98l.38 2.72c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.72c.61-.25 1.17-.58 1.69-.98l2.55 1.03c.22.08.49 0 .61-.22l2.04-3.53c.12-.22.07-.49-.12-.64l-2.16-1.68z"/>'
      + '</svg>';

    function makeCogBtn(settingsDiv) {{
      var btn = document.createElement('button');
      btn.className = 'legend-cog-btn';
      btn.title = 'Layer settings';
      btn.innerHTML = COG_SVG;
      btn.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isOpen = settingsDiv.classList.toggle('open');
        btn.classList.toggle('active', isOpen);
        if (isOpen) {{
          document.querySelectorAll('.layer-settings.open').forEach(function(el) {{
            if (el !== settingsDiv) el.classList.remove('open');
          }});
          document.querySelectorAll('.legend-cog-btn.active').forEach(function(el) {{
            if (el !== btn) el.classList.remove('active');
          }});
        }}
      }});
      return btn;
    }}

    function buildLayerRow(item, container) {{
      var ld = item.ld;
      var sm = ld.styleMap || {{}};
      var geomType = (ld.kind === 'raster' || ld.kind === 'wms') ? 'raster' : ld.geomType;
      var cfg = ld.labelConfig || null;

      var primaryStyle = {{}};
      if (sm.type === 'single') primaryStyle = sm.style || {{}};
      else if (sm.entries && sm.entries.length) primaryStyle = sm.entries[0].style || {{}};

      var hasEntries = sm.entries && sm.entries.length > 1;

      var layerDiv = document.createElement('div');
      layerDiv.className = 'legend-layer';

      // ── Main row ─────────────────────────────────────────────────────
      var row = document.createElement('div');
      row.className = 'legend-layer-row';

      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.title = 'Toggle layer visibility';
      cb.addEventListener('change', function() {{
        setLayerVisible(item, cb.checked);
      }});

      var swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.innerHTML = swatchSvg(geomType, primaryStyle);

      var nameEl = document.createElement('span');
      nameEl.className = 'legend-layer-name';
      nameEl.title = ld.name;
      nameEl.textContent = ld.name;

      row.appendChild(cb);
      row.appendChild(swatch);
      row.appendChild(nameEl);

      // ── Expand button (categories) ────────────────────────────────────
      var entriesDiv = null;
      if (hasEntries) {{
        var expBtn = document.createElement('span');
        expBtn.className = 'legend-expand';
        expBtn.textContent = '▶';
        expBtn.title = 'Expand / collapse categories';
        expBtn.addEventListener('click', function(e) {{
          e.stopPropagation();
          var open = entriesDiv.classList.toggle('open');
          expBtn.style.transform = open ? 'rotate(90deg)' : '';
        }});
        row.appendChild(expBtn);

        entriesDiv = document.createElement('div');
        entriesDiv.className = 'legend-entries';
        var classTogglable = sm.type === 'categorized' || sm.type === 'graduated';
        sm.entries.forEach(function(entry, ei) {{
          var eRow = document.createElement('div');
          eRow.className = 'legend-entry';
          if (classTogglable) {{
            var eCb = document.createElement('input');
            eCb.type = 'checkbox';
            eCb.checked = true;
            eCb.title = 'Toggle this class';
            (function(entryIndex, row) {{
              eCb.addEventListener('change', function() {{
                if (!eCb.checked) {{
                  if (item.hiddenClasses.indexOf(entryIndex) === -1)
                    item.hiddenClasses.push(entryIndex);
                  row.classList.add('class-hidden');
                }} else {{
                  var pos = item.hiddenClasses.indexOf(entryIndex);
                  if (pos !== -1) item.hiddenClasses.splice(pos, 1);
                  row.classList.remove('class-hidden');
                }}
                rebuildLayer(item);
              }});
            }})(ei, eRow);
            eRow.appendChild(eCb);
          }}
          var eSwatch = document.createElement('span');
          eSwatch.className = 'legend-swatch';
          eSwatch.innerHTML = swatchSvg(geomType, entry.style || {{}});
          var eLabel = document.createElement('span');
          eLabel.className = 'legend-entry-label';
          eLabel.title = entry.label || '';
          eLabel.textContent = entry.label || '';
          eRow.appendChild(eSwatch);
          eRow.appendChild(eLabel);
          entriesDiv.appendChild(eRow);
        }});
      }}

      // ── Settings panel (behind cog) ───────────────────────────────────
      var settingsDiv = document.createElement('div');
      settingsDiv.className = 'layer-settings';

      // Opacity row
      var opRow = document.createElement('div');
      opRow.className = 'layer-settings-row';
      var opLbl = document.createElement('span');
      opLbl.className = 'layer-settings-label';
      opLbl.textContent = 'Opacity';
      var slider = document.createElement('input');
      slider.type = 'range';
      slider.min = '0'; slider.max = '100'; slider.value = '100';
      slider.title = 'Layer opacity';
      slider.addEventListener('input', function() {{
        setLayerOpacity(item, parseInt(slider.value, 10) / 100);
      }});
      opRow.appendChild(opLbl);
      opRow.appendChild(slider);
      settingsDiv.appendChild(opRow);

      // Labels row (only for vector layers that have a label field)
      if (cfg && ld.kind === 'vector') {{
        var lblRow = document.createElement('div');
        lblRow.className = 'layer-settings-row';
        var lblLbl = document.createElement('span');
        lblLbl.className = 'layer-settings-label';
        lblLbl.textContent = 'Labels';
        var lblCb = document.createElement('input');
        lblCb.type = 'checkbox';
        lblCb.checked = cfg.enabled || false;
        lblCb.title = 'Toggle feature labels';
        lblCb.addEventListener('change', function() {{
          setLayerLabels(item, lblCb.checked);
        }});
        lblRow.appendChild(lblLbl);
        lblRow.appendChild(lblCb);
        settingsDiv.appendChild(lblRow);

        // Label placement mode selector (global — applies to all label layers)
        var modeRow = document.createElement('div');
        modeRow.className = 'layer-settings-row';
        var modeLbl = document.createElement('span');
        modeLbl.className = 'layer-settings-label';
        modeLbl.textContent = 'Placement';
        var modeSel = document.createElement('select');
        modeSel.className = 'label-mode-sel';
        modeSel.style.cssText = 'font-size:11px;flex:1;border:1px solid #ccc;border-radius:2px;padding:1px 3px;';
        modeSel.title = 'Label placement algorithm — applies to all label layers';
        [['candidate','Candidate (fast)'],['force','Force (smooth)']].forEach(function(opt) {{
          var o = document.createElement('option');
          o.value = opt[0]; o.textContent = opt[1];
          if (opt[0] === _labelPlacementMode) o.selected = true;
          modeSel.appendChild(o);
        }});
        modeSel.addEventListener('change', function() {{
          _labelPlacementMode = modeSel.value;
          document.querySelectorAll('.label-mode-sel').forEach(function(s) {{ s.value = _labelPlacementMode; }});
          layoutAllLabels();
        }});
        modeRow.appendChild(modeLbl);
        modeRow.appendChild(modeSel);
        settingsDiv.appendChild(modeRow);
      }}

      // Cluster row (point vector layers only)
      if (ld.kind === 'vector' && ld.geomType === 'point') {{
        var clRow = document.createElement('div');
        clRow.className = 'layer-settings-row';
        var clLbl = document.createElement('span');
        clLbl.className = 'layer-settings-label';
        clLbl.textContent = 'Cluster';
        var clCb = document.createElement('input');
        clCb.type = 'checkbox';
        clCb.checked = false;
        var clusterAvail = typeof L.markerClusterGroup !== 'undefined';
        clCb.title = clusterAvail ? 'Toggle marker clustering' : 'Marker cluster plugin not loaded';
        clCb.disabled = !clusterAvail;
        clCb.addEventListener('change', function() {{
          item.clusterEnabled = clCb.checked;
          rebuildLayer(item);
        }});
        clRow.appendChild(clLbl);
        clRow.appendChild(clCb);
        settingsDiv.appendChild(clRow);
      }}

      row.appendChild(makeCogBtn(settingsDiv));

      layerDiv.appendChild(row);
      if (entriesDiv) layerDiv.appendChild(entriesDiv);
      layerDiv.appendChild(settingsDiv);
      container.appendChild(layerDiv);
      item.checkbox = cb;
      item.layerDiv = layerDiv;
    }}

    function setGroupVisible(nodeList, visible) {{
      nodeList.forEach(function(node) {{
        if (node.type === 'layer') {{
          var it = displayItems[node.index];
          if (it) setLayerVisible(it, visible);
        }} else if (node.type === 'group') {{
          setGroupVisible(node.children, visible);
        }}
      }});
    }}

    function buildLegendNodes(nodes, container) {{
      nodes.forEach(function(node) {{
        if (node.type === 'group') {{
          var grpDiv = document.createElement('div');
          grpDiv.className = 'legend-group';
          var grpHdr = document.createElement('div');
          grpHdr.className = 'legend-group-hdr';

          // Visibility checkbox for the whole group
          var grpCb = document.createElement('input');
          grpCb.type = 'checkbox';
          grpCb.checked = true;
          grpCb.title = 'Toggle group visibility';
          grpCb.addEventListener('change', function() {{
            setGroupVisible(node.children, grpCb.checked);
          }});

          var grpExp = document.createElement('span');
          grpExp.className = 'legend-expand';
          grpExp.textContent = '▼';
          var grpName = document.createElement('span');
          grpName.className = 'legend-group-name';
          grpName.textContent = node.name;
          grpHdr.appendChild(grpCb);
          grpHdr.appendChild(grpExp);
          grpHdr.appendChild(grpName);
          var grpBody = document.createElement('div');
          grpBody.className = 'legend-group-body open';
          grpHdr.addEventListener('click', function(e) {{
            if (e.target === grpCb) return;
            var open = grpBody.classList.toggle('open');
            grpExp.textContent = open ? '▼' : '▶';
          }});
          grpDiv.appendChild(grpHdr);
          grpDiv.appendChild(grpBody);
          container.appendChild(grpDiv);
          buildLegendNodes(node.children, grpBody);
        }} else {{
          var item = displayItems[node.index];
          if (item) buildLayerRow(item, container);
        }}
      }});
    }}

    if (LAYER_TREE.length > 0) {{
      buildLegendNodes(LAYER_TREE, body);
    }} else {{
      displayItems.forEach(function(item) {{
        buildLayerRow(item, body);
      }});
    }}

    // ── Basemap entry (only when basemap is included) ─────────────────────────
    if (basemap) (function() {{
      var bDiv = document.createElement('div');
      bDiv.className = 'legend-layer';

      var bRow = document.createElement('div');
      bRow.className = 'legend-layer-row';

      var bSwatch = document.createElement('span');
      bSwatch.className = 'legend-swatch';
      bSwatch.innerHTML = '<svg width="20" height="16" xmlns="http://www.w3.org/2000/svg">'
        + '<rect x="1" y="1" width="18" height="14" fill="#e8e4dc" stroke="#bbb"/>'
        + '<path d="M1 11 L7 6 L11 9 L19 3" stroke="#8bbf8b" stroke-width="1.5" fill="none"/>'
        + '<circle cx="14" cy="11" r="1.5" fill="#7a9fd0"/></svg>';

      var bName = document.createElement('span');
      bName.className = 'legend-layer-name';
      bName.textContent = 'OpenStreetMap';
      bName.title = 'OpenStreetMap basemap';

      var bSettingsDiv = document.createElement('div');
      bSettingsDiv.className = 'layer-settings';
      var bOpRow = document.createElement('div');
      bOpRow.className = 'layer-settings-row';
      var bOpLbl = document.createElement('span');
      bOpLbl.className = 'layer-settings-label';
      bOpLbl.textContent = 'Opacity';
      var bSlider = document.createElement('input');
      bSlider.type = 'range';
      bSlider.min = '0'; bSlider.max = '100'; bSlider.value = '100';
      bSlider.title = 'Basemap opacity';
      bSlider.addEventListener('input', function() {{
        basemap.setOpacity(parseInt(bSlider.value, 10) / 100);
      }});
      bOpRow.appendChild(bOpLbl);
      bOpRow.appendChild(bSlider);
      bSettingsDiv.appendChild(bOpRow);

      bRow.appendChild(bSwatch);
      bRow.appendChild(bName);
      bRow.appendChild(makeCogBtn(bSettingsDiv));
      bDiv.appendChild(bRow);
      bDiv.appendChild(bSettingsDiv);
      body.appendChild(bDiv);
    }})();  // end basemap legend entry
  }} }} catch(legendErr) {{ console.error('Legend build failed:', legendErr); }}

  // ── Map-level click + drag-select ────────────────────────────────────────
  var selectRect = document.getElementById('select-rect');
  var _dragStart = null, _dragRx, _dragRy, _dragRw, _dragRh;

  map.getContainer().addEventListener('mousedown', function(e) {{
    if (!_selectMode || e.button !== 0) return;
    e.preventDefault();
    map.dragging.disable();
    var rc = map.getContainer().getBoundingClientRect();
    _dragStart = {{x: e.clientX - rc.left, y: e.clientY - rc.top}};
    selectRect.style.cssText += ';left:'+_dragStart.x+'px;top:'+_dragStart.y+'px;width:0;height:0;display:block';
  }});

  document.addEventListener('mousemove', function(e) {{
    if (!_selectMode || !_dragStart) return;
    var rc = map.getContainer().getBoundingClientRect();
    var cx = e.clientX - rc.left, cy = e.clientY - rc.top;
    _dragRx = Math.min(_dragStart.x, cx); _dragRy = Math.min(_dragStart.y, cy);
    _dragRw = Math.abs(cx - _dragStart.x); _dragRh = Math.abs(cy - _dragStart.y);
    selectRect.style.left = _dragRx+'px'; selectRect.style.top = _dragRy+'px';
    selectRect.style.width = _dragRw+'px'; selectRect.style.height = _dragRh+'px';
  }});

  document.addEventListener('mouseup', function(e) {{
    if (!_selectMode || !_dragStart) return;
    map.dragging.enable();
    selectRect.style.display = 'none';
    _dragStart = null;
    if (!_dragRw || _dragRw < 5 || _dragRh < 5) return;

    var sw = map.containerPointToLatLng(L.point(_dragRx, _dragRy + _dragRh));
    var ne = map.containerPointToLatLng(L.point(_dragRx + _dragRw, _dragRy));
    var bounds = L.latLngBounds(sw, ne);

    // Find the active layer (attr table selection or first visible vector)
    var selIdx = parseInt(attrTableLayer.value, 10);
    var targetItem = null;
    legendItems.forEach(function(it) {{ if (it.index === selIdx && it.ld.kind === 'vector') targetItem = it; }});
    if (!targetItem) legendItems.forEach(function(it) {{ if (!targetItem && it.ld.kind === 'vector' && it.visible) targetItem = it; }});
    if (!targetItem) return;

    var selSet = [];
    targetItem.ld.geojson.features.forEach(function(feat, fi) {{
      if (!feat.geometry) return;
      var coords = feat.geometry.type === 'Point' ? [feat.geometry.coordinates]
                 : feat.geometry.type === 'MultiPoint' ? feat.geometry.coordinates : null;
      if (coords) {{
        for (var ci = 0; ci < coords.length; ci++) {{
          if (bounds.contains(L.latLng(coords[ci][1], coords[ci][0]))) {{ selSet.push(fi); return; }}
        }}
      }} else {{
        try {{
          var center = L.geoJSON(feat).getBounds().getCenter();
          if (bounds.contains(center)) selSet.push(fi);
        }} catch(ex) {{}}
      }}
    }});

    if (!selSet.length) return;
    attrTableLayer.value = targetItem.index;
    _attrSelectSet = selSet;
    populateAttrTable();
    attrTablePanel.classList.add('open');
  }});

  // ── Click identify ────────────────────────────────────────────────────────
  map.on('click', function(e) {{
    if (_selectMode) return;
    var clickPt = map.latLngToContainerPoint(e.latlng);
    var found = [];
    legendItems.forEach(function(it) {{
      if (!it.visible || it.ld.kind !== 'vector') return;
      it.lfl.eachLayer(function(fl) {{
        if (!fl._infoHtml) return;
        var latlng = fl.getLatLng ? fl.getLatLng()
                   : (fl.getBounds ? fl.getBounds().getCenter() : null);
        if (!latlng) return;
        var pt = map.latLngToContainerPoint(latlng);
        var d = Math.sqrt(Math.pow(pt.x - clickPt.x, 2) + Math.pow(pt.y - clickPt.y, 2));
        if (d <= 10) found.push({{layerName: it.ld.name, html: fl._infoHtml, lfl: fl, legendItem: it}});
      }});
    }});
    if (!found.length) return;

    function getDisplayName(f) {{
      var props = f.lfl._feature && f.lfl._feature.properties || {{}};
      var vals = Object.values(props).filter(function(v) {{ return v != null && v !== ''; }});
      return vals.length ? String(vals[0]) : '(feature)';
    }}

    function showSingle(f) {{
      infoPanel.classList.remove('split');
      infoPanelBody.innerHTML = f.html;
      highlightFeatureOnMap(f.lfl._feature);
    }}

    function showSplit() {{
      infoPanel.classList.add('split');
      infoPanelBody.innerHTML = '';

      var splitDiv = document.createElement('div');
      splitDiv.className = 'info-split';

      var listPane = document.createElement('div');
      listPane.className = 'info-list-pane';

      var detailPane = document.createElement('div');
      detailPane.className = 'info-detail-pane';

      found.forEach(function(f) {{
        var item = document.createElement('div');
        item.className = 'mf-item';
        var fStyle = resolveStyle(f.legendItem.ld.styleMap, f.lfl._feature && f.lfl._feature.properties || {{}});
        var fSwatch = swatchSvg(f.legendItem.ld.geomType, fStyle);
        item.innerHTML = '<span class="mf-swatch">'+fSwatch+'</span>'
                       + '<span class="mf-text">'
                       + '<div class="mf-feature-name">'+escHtml(getDisplayName(f))+'</div>'
                       + '<div class="mf-layer-name">'+escHtml(f.layerName)+'</div>'
                       + '</span>';
        item.addEventListener('click', function() {{
          listPane.querySelectorAll('.mf-item').forEach(function(el) {{ el.classList.remove('active'); }});
          item.classList.add('active');
          detailPane.innerHTML = f.html;
          highlightFeatureOnMap(f.lfl._feature);
        }});
        listPane.appendChild(item);
      }});

      splitDiv.appendChild(listPane);
      splitDiv.appendChild(detailPane);
      infoPanelBody.appendChild(splitDiv);
      listPane.querySelector('.mf-item').click();
    }}

    if (found.length === 1) showSingle(found[0]); else showSplit();
    infoPanel.classList.add('open');
  }});

  // ── Populate attribute table layer selector ───────────────────────────────
  legendItems.forEach(function(it) {{
    if (it.ld.kind !== 'vector') return;
    var o = document.createElement('option');
    o.value = it.index; o.textContent = it.ld.name;
    attrTableLayer.appendChild(o);
  }});
  attrTableLayer.addEventListener('change', function() {{
    if (attrTableSearch) attrTableSearch.value = '';
    populateAttrTable();
  }});

  function setLayerVisible(item, visible) {{
    item.visible = visible;
    if (visible) item.lfl.addTo(map);
    else map.removeLayer(item.lfl);
    if (item.checkbox) item.checkbox.checked = visible;
    if (item.layerDiv) item.layerDiv.classList.toggle('hidden', !visible);
    if (item.labelGroup) item.labelGroup.style.display = (visible && item.labelsVisible) ? '' : 'none';
    setTimeout(layoutAllLabels, 100);
  }}

  function setLayerOpacity(item, factor) {{
    var pane = map.getPane(item.paneName);
    if (pane) pane.style.opacity = factor;
  }}

  function setLayerLabels(item, visible) {{
    item.labelsVisible = visible;
    if (item.labelGroup) item.labelGroup.style.display = (item.visible && visible) ? '' : 'none';
    setTimeout(layoutAllLabels, 100);
  }}

  // ── Label placement helpers ───────────────────────────────────────────────
  function _lblDims(text, fontSize) {{
    return {{ w: text.length * fontSize * 0.55 + 8, h: fontSize * 1.4 }};
  }}

  function _lblOverlap(ax, ay, aw, ah, bx, by, bw, bh) {{
    var ox = Math.max(0, (aw + bw) / 2 + 3 - Math.abs(ax - bx));
    var oy = Math.max(0, (ah + bh) / 2 + 3 - Math.abs(ay - by));
    return ox * oy;
  }}

  function _candidatePlacement(labels) {{
    var DIRS = [
      [0,-1],[0.71,-0.71],[1,0],[0.71,0.71],
      [0,1],[-0.71,0.71],[-1,0],[-0.71,-0.71]
    ];
    var placed = [];
    labels.forEach(function(lbl) {{
      var baseR = lbl.h * 0.55 + 6;
      var best = null, bestScore = Infinity;
      [1.0, 1.7, 2.6].forEach(function(rm) {{
        DIRS.forEach(function(d) {{
          var cx = lbl.ax + d[0] * (lbl.w / 2 + baseR * rm);
          var cy = lbl.ay + d[1] * (lbl.h / 2 + baseR * rm);
          var score = 0;
          placed.forEach(function(p) {{
            score += _lblOverlap(cx, cy, lbl.w, lbl.h, p.x, p.y, p.w, p.h);
          }});
          score += Math.sqrt(Math.pow(cx-lbl.ax,2)+Math.pow(cy-lbl.ay,2)) * 0.08;
          if (score < bestScore) {{ bestScore = score; best = {{x:cx,y:cy}}; }}
        }});
      }});
      lbl.x = best.x; lbl.y = best.y;
      placed.push(lbl);
    }});
  }}

  function _forcePlacement(labels) {{
    _candidatePlacement(labels); // warm start
    labels.forEach(function(l) {{ l.vx = 0; l.vy = 0; }});
    for (var iter = 0; iter < 45; iter++) {{
      var alpha = 1 - iter / 45;
      labels.forEach(function(li) {{
        li.vx += (li.ax - li.x) * 0.035 * alpha;
        li.vy += (li.ay - li.y) * 0.035 * alpha;
        labels.forEach(function(lj) {{
          if (li === lj) return;
          var ov = _lblOverlap(li.x, li.y, li.w, li.h, lj.x, lj.y, lj.w, lj.h);
          if (!ov) return;
          var dx = (li.x - lj.x) || 0.1, dy = (li.y - lj.y) || 0.1;
          var dist = Math.sqrt(dx*dx + dy*dy);
          var f = Math.sqrt(ov) * 0.75;
          li.vx += dx/dist*f; li.vy += dy/dist*f;
        }});
        li.vx *= 0.62; li.vy *= 0.62;
        li.x += li.vx; li.y += li.vy;
      }});
    }}
  }}

  // ── SVG label render pass ─────────────────────────────────────────────────
  function layoutAllLabels() {{
    if (!_labelSvg) return;
    var all = [];
    _allLabelItems.forEach(function(item) {{
      if (!item.visible || !item.labelsVisible || !item.labelData) return;
      var cfg = item.labelCfg;
      var fsz = cfg.fontSize || 11;
      item.labelData.forEach(function(ld) {{
        var pt = map.latLngToContainerPoint(ld.latlng);
        var dims = _lblDims(ld.text, fsz);
        all.push({{
          text: ld.text, cfg: cfg,
          ax: pt.x, ay: pt.y,
          x: pt.x, y: pt.y - dims.h * 0.6,
          w: dims.w, h: dims.h,
          vx: 0, vy: 0,
          group: item.labelGroup
        }});
      }});
    }});

    // Clear SVG groups
    _allLabelItems.forEach(function(item) {{
      if (item.labelGroup) item.labelGroup.innerHTML = '';
    }});
    if (!all.length) return;

    if (_labelPlacementMode === 'force') {{
      _forcePlacement(all);
    }} else {{
      _candidatePlacement(all);
    }}

    // Render labels and callouts
    var NS = 'http://www.w3.org/2000/svg';
    all.forEach(function(lbl) {{
      if (!lbl.group) return;
      var cfg = lbl.cfg;
      var fsz = cfg.fontSize || 11;
      var g = document.createElementNS(NS, 'g');

      // Dashed callout line when displaced > 8 px
      var dx = lbl.x - lbl.ax, dy = lbl.y - lbl.ay;
      if (Math.sqrt(dx*dx + dy*dy) > 8) {{
        var line = document.createElementNS(NS, 'line');
        line.setAttribute('x1', lbl.ax.toFixed(1));
        line.setAttribute('y1', lbl.ay.toFixed(1));
        line.setAttribute('x2', lbl.x.toFixed(1));
        line.setAttribute('y2', lbl.y.toFixed(1));
        line.setAttribute('stroke', cfg.fontColor || '#333');
        line.setAttribute('stroke-width', '0.9');
        line.setAttribute('stroke-opacity', '0.45');
        line.setAttribute('stroke-dasharray', '2,2');
        g.appendChild(line);
      }}

      var t = document.createElementNS(NS, 'text');
      t.setAttribute('x', lbl.x.toFixed(1));
      t.setAttribute('y', lbl.y.toFixed(1));
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'central');
      t.setAttribute('font-size', fsz + 'px');
      t.setAttribute('font-family', (cfg.fontFamily || 'Arial') + ', Arial, sans-serif');
      t.setAttribute('fill', cfg.fontColor || '#000');
      t.setAttribute('fill-opacity', cfg.fontOpacity != null ? cfg.fontOpacity : 1);
      if (cfg.bold) t.setAttribute('font-weight', 'bold');
      if (cfg.italic) t.setAttribute('font-style', 'italic');
      if (cfg.bufferSize > 0) {{
        t.setAttribute('stroke', cfg.bufferColor || '#fff');
        t.setAttribute('stroke-width', (cfg.bufferSize * 1.5) + 'px');
        t.setAttribute('paint-order', 'stroke fill');
        t.setAttribute('stroke-linejoin', 'round');
      }}
      t.textContent = lbl.text;
      g.appendChild(t);
      lbl.group.appendChild(g);
    }});
  }}

  function buildLabels(item) {{
    var ld = item.ld;
    if (!ld.labelConfig || ld.kind !== 'vector') return;
    var cfg = ld.labelConfig;

    // Collect label anchor points from rendered features
    var labelData = [];
    item.lfl.eachLayer(function(fl) {{
      var props = fl.feature && fl.feature.properties;
      if (!props) return;
      var val = props[cfg.field];
      if (val == null || val === '') return;
      var latlng = fl.getLatLng ? fl.getLatLng()
                 : (fl.getBounds ? fl.getBounds().getCenter() : null);
      if (latlng) labelData.push({{ text: String(val), latlng: latlng }});
    }});
    item.labelData = labelData;
    item.labelCfg = cfg;

    // Replace any old SVG group for this item
    if (item.labelGroup && item.labelGroup.parentNode) {{
      item.labelGroup.parentNode.removeChild(item.labelGroup);
    }}
    var NS = 'http://www.w3.org/2000/svg';
    var g = document.createElementNS(NS, 'g');
    g.style.display = (item.visible && item.labelsVisible) ? '' : 'none';
    if (_labelSvg) _labelSvg.appendChild(g);
    item.labelGroup = g;

    if (_allLabelItems.indexOf(item) === -1) _allLabelItems.push(item);
    map.off('moveend zoomend viewreset', layoutAllLabels);
    map.on('moveend zoomend viewreset', layoutAllLabels);
    setTimeout(layoutAllLabels, 150);
  }}

  // ── Filter toolbar ─────────────────────────────────────────────────────────
  (function initFilter() {{
    var vectorItems = legendItems.filter(function(it) {{ return it.ld.kind === 'vector'; }});
    if (vectorItems.length === 0) return;

    var bar          = document.getElementById('filterbar');
    var layerSel     = document.getElementById('filter-layer');
    var attrSel      = document.getElementById('filter-attr');
    var valuesBtn    = document.getElementById('filter-values-btn');
    var valuesPanel  = document.getElementById('filter-values-panel');
    var valuesSearch = document.getElementById('filter-values-search');
    var valuesList   = document.getElementById('filter-values-list');
    var clearBtn     = document.getElementById('filter-clear');
    var countEl      = document.getElementById('filter-count');

    // Create the filter toggle as a Leaflet control so it stacks with other controls
    var FilterToggle = L.Control.extend({{
      onAdd: function() {{
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-filter');
        btn.title = 'Toggle attribute filter';
        btn.setAttribute('aria-label', 'Toggle attribute filter');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">'
          + '<path d="M2 3h14l-5 5.5V15l-4-2V8.5z" fill="#555" stroke="#444" stroke-width="0.5" stroke-linejoin="round"/></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {{
          var isOpen = bar.style.display === 'flex';
          bar.style.display = isOpen ? 'none' : 'flex';
          btn.classList.toggle('active', !isOpen);
        }});
        return btn;
      }}
    }});
    new FilterToggle({{ position: 'topleft' }}).addTo(map);

    // Populate layer dropdown (value = index into legendItems)
    vectorItems.forEach(function(it) {{
      var o = document.createElement('option');
      o.value = it.index;
      o.textContent = it.ld.name;
      layerSel.appendChild(o);
    }});

    function currentItem() {{
      return legendItems[parseInt(layerSel.value, 10)];
    }}

    function checkedValues() {{
      var out = [];
      Array.prototype.forEach.call(valuesList.querySelectorAll('input:checked'), function(c) {{
        out.push(c.value);
      }});
      return out;
    }}

    function updateValuesBtn() {{
      var sel = checkedValues();
      if (sel.length) valuesBtn.textContent = sel.length + ' selected';
      else if (valuesSearch.value.trim()) valuesBtn.textContent = 'contains: ' + valuesSearch.value.trim();
      else valuesBtn.textContent = 'All values';
    }}

    function updateCount(item) {{
      var total = item.ld.geojson.features.length;
      var shown = item.filterFn ? item.ld.geojson.features.filter(item.filterFn).length : total;
      countEl.textContent = shown + ' / ' + total;
    }}

    function clearOtherFilters(keep) {{
      legendItems.forEach(function(it) {{
        if (it !== keep && it.filterFn) {{ it.filterFn = null; rebuildLayer(it); }}
      }});
    }}

    function applyFilter() {{
      var item = currentItem();
      if (!item) return;
      var attr = attrSel.value;
      var search = valuesSearch.value.trim().toLowerCase();
      var selected = checkedValues();
      if (!attr || (selected.length === 0 && !search)) {{
        item.filterFn = null;
      }} else {{
        item.filterFn = function(feature) {{
          var v = (feature.properties || {{}})[attr];
          var sv = (v == null ? '' : String(v));
          if (selected.length) return selected.indexOf(sv) !== -1;
          return sv.toLowerCase().indexOf(search) !== -1;
        }};
      }}
      rebuildLayer(item);
      updateCount(item);
    }}

    function populateAttrs() {{
      var item = currentItem();
      attrSel.innerHTML = '';
      if (!item) return;
      var feats = item.ld.geojson.features;
      var keys = [], seen = {{}};
      for (var i = 0; i < Math.min(feats.length, 50); i++) {{
        var p = feats[i].properties || {{}};
        for (var k in p) {{ if (!(k in seen)) {{ seen[k] = 1; keys.push(k); }} }}
      }}
      keys.forEach(function(k) {{
        var o = document.createElement('option');
        o.value = k; o.textContent = k;
        attrSel.appendChild(o);
      }});
    }}

    function populateValues() {{
      var item = currentItem();
      var attr = attrSel.value;
      valuesList.innerHTML = '';
      valuesSearch.value = '';
      if (!item || !attr) {{ updateValuesBtn(); return; }}
      var feats = item.ld.geojson.features;
      var seen = {{}}, vals = [];
      for (var i = 0; i < feats.length; i++) {{
        var v = (feats[i].properties || {{}})[attr];
        var sv = (v == null ? '' : String(v));
        if (!(sv in seen)) {{ seen[sv] = 1; vals.push(sv); }}
        if (vals.length > 2000) break;
      }}
      vals.sort(function(a, b) {{
        var na = parseFloat(a), nb = parseFloat(b);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return a < b ? -1 : (a > b ? 1 : 0);
      }});
      vals.forEach(function(val) {{
        var lab = document.createElement('label');
        lab.className = 'filter-value-item';
        var c = document.createElement('input');
        c.type = 'checkbox'; c.value = val;
        c.addEventListener('change', function() {{ applyFilter(); updateValuesBtn(); }});
        var s = document.createElement('span');
        s.textContent = (val === '' ? '(empty)' : val);
        s.title = val;
        lab.appendChild(c); lab.appendChild(s);
        valuesList.appendChild(lab);
      }});
      updateValuesBtn();
    }}

    // Events
    layerSel.addEventListener('change', function() {{
      var item = currentItem();
      clearOtherFilters(item);
      populateAttrs();
      populateValues();
      applyFilter();
    }});
    attrSel.addEventListener('change', function() {{
      populateValues();
      applyFilter();
    }});
    valuesSearch.addEventListener('input', function() {{
      var q = valuesSearch.value.trim().toLowerCase();
      Array.prototype.forEach.call(valuesList.children, function(el) {{
        el.style.display = el.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
      }});
      applyFilter();
      updateValuesBtn();
    }});
    valuesBtn.addEventListener('click', function() {{
      valuesPanel.classList.toggle('open');
    }});
    document.addEventListener('click', function(e) {{
      if (!document.getElementById('filter-values-wrap').contains(e.target)) {{
        valuesPanel.classList.remove('open');
      }}
    }});
    clearBtn.addEventListener('click', function() {{
      valuesSearch.value = '';
      Array.prototype.forEach.call(valuesList.querySelectorAll('input:checked'), function(c) {{
        c.checked = false;
      }});
      Array.prototype.forEach.call(valuesList.children, function(el) {{ el.style.display = ''; }});
      applyFilter();
      updateValuesBtn();
    }});

    // Initialise with the first vector layer
    populateAttrs();
    populateValues();
    var first = currentItem();
    if (first) updateCount(first);
  }})();

  // ── Map Views (header items below description, above doc metadata) ──────────
  if (THEMES.length > 0) {{
    function applyTheme(idx) {{
      var theme = THEMES[idx];
      if (!theme) return;
      if (theme.layerIds) {{
        legendItems.forEach(function(it) {{
          var vis = theme.layerIds.indexOf(it.ld.name) !== -1;
          setLayerVisible(it, vis);
          if (it.checkbox) it.checkbox.checked = vis;
          if (it.layerDiv) it.layerDiv.classList.toggle('hidden', !vis);
        }});
      }}
      if (theme.extent) {{
        try {{ map.fitBounds(theme.extent, {{padding: [20, 20]}}); }} catch(e) {{}}
      }}
    }}

    var mvSection = document.getElementById('map-views-section');
    if (mvSection) {{
      THEMES.forEach(function(th, i) {{
        var item = document.createElement('div');
        item.className = 'mv-item';
        item.innerHTML = '<div class="mv-item-name">' + escHtml(th.name || 'Map View ' + (i + 1)) + '</div>'
                       + (th.notes ? '<div class="mv-item-notes">' + escHtml(th.notes) + '</div>' : '');
        item.addEventListener('click', function() {{
          mvSection.querySelectorAll('.mv-item').forEach(function(el) {{ el.classList.remove('active'); }});
          item.classList.add('active');
          applyTheme(i);
        }});
        mvSection.appendChild(item);
      }});
    }}
  }}

  // ── Brand watermark (bottomleft Leaflet control, above scale bar) ─────────
  var BrandControl = L.Control.extend({{
    onAdd: function() {{
      var div = L.DomUtil.create('div', 'brand-watermark leaflet-control');
      div.style.pointerEvents = 'none';  // don't absorb map mouse events
      div.innerHTML = {brand_content_json};
      return div;
    }}
  }});
  new BrandControl({{position: 'bottomleft'}}).addTo(map);

}})();
</script>
</body>
</html>"""


def _flatten_coords(geom):
    """Yield all [x, y] coordinate pairs from a GeoJSON geometry dict."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Point":
        if coords:
            yield coords
    elif gtype in ("MultiPoint", "LineString"):
        for c in coords:
            yield c
    elif gtype in ("MultiLineString", "Polygon"):
        for ring in coords:
            for c in ring:
                yield c
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for c in ring:
                    yield c
    elif gtype == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from _flatten_coords(g)
