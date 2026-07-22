"""
Translate QGIS renderers and symbol layers into the web map's style dicts.

A styleMap maps a category key (or "__default__") to a flat dict of
Leaflet-compatible style attributes; the JS side interprets extras such as
hatch patterns, marker SVG and dash arrays.
"""
from typing import Optional

from qgis.core import (
    QgsSymbol, QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsGraduatedSymbolRenderer, QgsRuleBasedRenderer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsSvgMarkerSymbolLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .compat import (
    _QgsGradientFill, _QgsLinePatternFill,
    _QgsPointPatternFill, _QgsSVGFill, _QgsShapeburstFill, _QgsCentroidFill,
    _QgsMarkerLine, _QgsHashedLine,
)
from .utils import _color_to_hex, _size_to_px
from .markers import _encode_marker_shape, _render_marker_symbol_to_svg



# Qt hatch brush styles → tileable pattern kinds understood by the JS side
_HATCH_BRUSH_KINDS = {
    Qt.HorPattern: "hor", Qt.VerPattern: "ver", Qt.CrossPattern: "cross",
    Qt.BDiagPattern: "bdiag", Qt.FDiagPattern: "fdiag",
    Qt.DiagCrossPattern: "diagcross",
}

# Qt density brushes → approximate coverage fraction (used to scale opacity)
_DENSE_BRUSH_FACTORS = {
    Qt.Dense1Pattern: 0.9, Qt.Dense2Pattern: 0.75, Qt.Dense3Pattern: 0.6,
    Qt.Dense4Pattern: 0.5, Qt.Dense5Pattern: 0.35, Qt.Dense6Pattern: 0.2,
    Qt.Dense7Pattern: 0.1,
}


def _pen_style_dash(pen) -> Optional[str]:
    """Translate a Qt pen style to an SVG/Leaflet dashArray string."""
    if pen == Qt.DashLine:
        return "8 4"
    if pen == Qt.DotLine:
        return "2 4"
    if pen == Qt.DashDotLine:
        return "8 4 2 4"
    if pen == Qt.DashDotDotLine:
        return "8 4 2 4 2 4"
    return None


def _snap_hatch_angle(angle) -> str:
    """Snap a line-pattern angle (degrees) to the nearest supported hatch kind."""
    a = float(angle) % 180.0
    if a < 22.5 or a >= 157.5:
        return "hor"
    if a < 67.5:
        return "bdiag"   # rising lines (/)
    if a < 112.5:
        return "ver"
    return "fdiag"        # falling lines (\)


def _blend_hex(c1, c2):
    """Mid-point blend of two QColors as hex (gradient fill fallback)."""
    return "#{:02x}{:02x}{:02x}".format(
        (c1.red() + c2.red()) // 2,
        (c1.green() + c2.green()) // 2,
        (c1.blue() + c2.blue()) // 2,
    )


def _sl_enabled(sl) -> bool:
    try:
        return bool(sl.enabled())
    except Exception:
        return True


def _extract_fill_symbol_style(symbol, sym_opacity) -> dict:
    """
    Extract polygon style by walking ALL symbol layers of a Fill symbol.

    Unlike marker/line symbols, QGIS polygon symbols routinely combine
    several layers (e.g. a fill layer plus a separate Simple Line outline)
    and use non-solid brushes (hatch, no-brush) and pattern fills.  The
    first fill-contributing layer wins the fill; the first stroke source
    wins the outline.
    """
    style = {}
    have_fill = False
    have_stroke = False

    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)
        if not _sl_enabled(sl):
            continue

        if isinstance(sl, QgsSimpleFillSymbolLayer):
            if not have_fill:
                try:
                    brush = sl.brushStyle()
                except Exception:
                    brush = Qt.SolidPattern
                fill_color = sl.fillColor()
                if brush == Qt.NoBrush:
                    pass  # outline-only layer: contributes no fill
                elif brush in _HATCH_BRUSH_KINDS:
                    style["fillHatch"] = {
                        "kind": _HATCH_BRUSH_KINDS[brush],
                        "color": _color_to_hex(fill_color),
                        "opacity": round(fill_color.alphaF() * sym_opacity, 3),
                        "width": 1, "spacing": 6,
                    }
                    have_fill = True
                elif brush in _DENSE_BRUSH_FACTORS:
                    style["fillColor"] = _color_to_hex(fill_color)
                    style["fillOpacity"] = round(
                        fill_color.alphaF() * sym_opacity * _DENSE_BRUSH_FACTORS[brush], 3)
                    have_fill = True
                else:  # solid / texture / unknown → solid colour
                    style["fillColor"] = _color_to_hex(fill_color)
                    style["fillOpacity"] = round(fill_color.alphaF() * sym_opacity, 3)
                    have_fill = True
            if not have_stroke:
                try:
                    pen = sl.strokeStyle()
                except Exception:
                    pen = Qt.SolidLine
                if pen != Qt.NoPen:
                    stroke_color = sl.strokeColor()
                    style["color"] = _color_to_hex(stroke_color)
                    style["opacity"] = round(stroke_color.alphaF() * sym_opacity, 3)
                    style["weight"] = round(
                        max(0.0, _size_to_px(sl.strokeWidth(), sl.strokeWidthUnit())), 1) or 1
                    dash = _pen_style_dash(pen)
                    if dash:
                        style["dashArray"] = dash
                    have_stroke = True

        elif isinstance(sl, QgsSimpleLineSymbolLayer):
            # Outline drawn as a separate line layer inside the fill symbol —
            # this must NOT zero the fill (the old code did exactly that).
            if not have_stroke:
                try:
                    pen = sl.penStyle()
                except Exception:
                    pen = Qt.SolidLine
                if pen != Qt.NoPen:
                    color = sl.color()
                    style["color"] = _color_to_hex(color)
                    style["opacity"] = round(color.alphaF() * sym_opacity, 3)
                    style["weight"] = round(max(0.5, _size_to_px(sl.width(), sl.widthUnit())), 1)
                    dash = _pen_style_dash(pen)
                    if dash:
                        style["dashArray"] = dash
                    elif pen == Qt.CustomDashLine:
                        try:
                            dv = sl.customDashVector()
                            unit = sl.customDashPatternUnit()
                            parts = [str(round(_size_to_px(v, unit), 1)) for v in dv]
                            if parts:
                                style["dashArray"] = " ".join(parts)
                        except Exception:
                            pass
                    have_stroke = True

        elif _QgsLinePatternFill is not None and isinstance(sl, _QgsLinePatternFill):
            if not have_fill:
                try:
                    sub = sl.subSymbol()
                    line_color = sub.color() if sub else sl.color()
                    line_w = 1.0
                    if sub and sub.symbolLayerCount():
                        lsl = sub.symbolLayer(0)
                        if isinstance(lsl, QgsSimpleLineSymbolLayer):
                            line_w = max(0.5, _size_to_px(lsl.width(), lsl.widthUnit()))
                    spacing = max(3.0, _size_to_px(sl.distance(), sl.distanceUnit()))
                    style["fillHatch"] = {
                        "kind": _snap_hatch_angle(sl.lineAngle()),
                        "color": _color_to_hex(line_color),
                        "opacity": round(line_color.alphaF() * sym_opacity, 3),
                        "width": round(line_w, 1),
                        "spacing": round(spacing, 1),
                    }
                    have_fill = True
                except Exception:
                    pass

        elif _QgsPointPatternFill is not None and isinstance(sl, _QgsPointPatternFill):
            if not have_fill:
                try:
                    sub = sl.subSymbol()
                    dot_color = sub.color() if sub else QColor(0, 0, 0)
                    dot_size = 2.0
                    if sub and sub.symbolLayerCount():
                        msl = sub.symbolLayer(0)
                        if isinstance(msl, QgsSimpleMarkerSymbolLayer):
                            dot_size = max(1.0, _size_to_px(msl.size(), msl.sizeUnit()))
                    dx = _size_to_px(sl.distanceX(), sl.distanceXUnit())
                    dy = _size_to_px(sl.distanceY(), sl.distanceYUnit())
                    style["fillHatch"] = {
                        "kind": "dots",
                        "color": _color_to_hex(dot_color),
                        "opacity": round(dot_color.alphaF() * sym_opacity, 3),
                        "size": round(dot_size, 1),
                        "spacing": round(max(3.0, dx, dy), 1),
                    }
                    have_fill = True
                except Exception:
                    pass

        elif _QgsGradientFill is not None and isinstance(sl, _QgsGradientFill):
            if not have_fill:
                try:
                    c1, c2 = sl.color(), sl.color2()
                    style["fillColor"] = _blend_hex(c1, c2)
                    style["fillOpacity"] = round(
                        (c1.alphaF() + c2.alphaF()) / 2.0 * sym_opacity, 3)
                    have_fill = True
                except Exception:
                    pass

        elif _QgsShapeburstFill is not None and isinstance(sl, _QgsShapeburstFill):
            if not have_fill:
                c = sl.color()
                style["fillColor"] = _color_to_hex(c)
                style["fillOpacity"] = round(c.alphaF() * sym_opacity, 3)
                have_fill = True

        elif _QgsSVGFill is not None and isinstance(sl, _QgsSVGFill):
            if not have_fill:
                try:
                    c = sl.svgFillColor()
                    style["fillColor"] = _color_to_hex(c)
                    style["fillOpacity"] = round(c.alphaF() * sym_opacity * 0.6, 3)
                    have_fill = True
                except Exception:
                    pass

        elif _QgsCentroidFill is not None and isinstance(sl, _QgsCentroidFill):
            continue  # centroid markers contribute neither fill nor outline

    if not have_fill and "fillHatch" not in style:
        style["fillOpacity"] = 0
    if not have_stroke and not have_fill:
        # Nothing usable found — fall back to the flattened symbol colour
        c = symbol.color()
        style["fillColor"] = _color_to_hex(c)
        style["fillOpacity"] = round(c.alphaF() * sym_opacity, 3)
        style["color"] = "#000000"
        style["weight"] = 1
        style["opacity"] = 1
    elif not have_stroke:
        # Borderless polygon: match QGIS by drawing no outline
        style["color"] = style.get("fillColor", "#000000")
        style["opacity"] = 0.0
        style["weight"] = 0
    return style


def _line_dash_array(sl):
    """SVG/Leaflet dashArray for a simple line layer, or None for solid."""
    try:
        pen = sl.penStyle()
    except Exception:
        return None
    if pen == Qt.CustomDashLine:
        try:
            dv = sl.customDashVector()
            unit = sl.customDashPatternUnit()
            parts = [str(round(_size_to_px(v, unit), 1)) for v in dv]
            return " ".join(parts) if parts else None
        except Exception:
            return None
    return _pen_style_dash(pen)


def _simple_line_stroke(sl, sym_opacity) -> dict:
    """One simple line layer → a web stroke dict (colour, width, dash)."""
    color = sl.color()
    stroke = {
        "color":   _color_to_hex(color),
        "opacity": round(color.alphaF() * sym_opacity, 3),
        "weight":  round(max(0.5, _size_to_px(sl.width(), sl.widthUnit())), 1),
    }
    dash = _line_dash_array(sl)
    if dash:
        stroke["dashArray"] = dash
    return stroke


def _templated_line_stroke(sl, sym_opacity):
    """Approximate a marker/hashed line — markers or ticks repeated along the
    line — as a 'tick' stroke the web app draws as perpendicular hash marks.
    Colour comes from the sub-symbol so it matches QGIS."""
    col = None
    try:
        sub = sl.subSymbol()
        if sub is not None:
            col = sub.color()
    except Exception:
        col = None
    if col is None:
        try:
            col = sl.color()
        except Exception:
            return None
    stroke = {
        "tick":    True,
        "color":   _color_to_hex(col),
        "opacity": round(col.alphaF() * sym_opacity, 3),
    }
    try:
        stroke["interval"] = max(2.0, round(_size_to_px(sl.interval(), sl.intervalUnit()), 1))
    except Exception:
        stroke["interval"] = 8.0
    # tick length: hashed lines expose hashLength; marker lines fall back to
    # the sub-symbol's marker size.
    tick_len = None
    try:
        tick_len = _size_to_px(sl.hashLength(), sl.hashLengthUnit())
    except Exception:
        tick_len = None
    if tick_len is None:
        try:
            sub = sl.subSymbol()
            if sub is not None:
                tick_len = _size_to_px(sub.size(), sub.sizeUnit())
        except Exception:
            tick_len = None
    stroke["tickLen"] = round(tick_len, 1) if tick_len else 6.0
    # tick line width from the sub-symbol's first layer, if it is a line
    weight = None
    try:
        sub = sl.subSymbol()
        if sub is not None and sub.symbolLayerCount():
            sub_sl = sub.symbolLayer(0)
            if hasattr(sub_sl, "width"):
                weight = _size_to_px(sub_sl.width(), sub_sl.widthUnit())
    except Exception:
        weight = None
    stroke["weight"] = round(max(0.5, weight), 1) if weight else 1.5
    try:
        stroke["tickAngle"] = round(float(sl.hashAngle()), 1)
    except Exception:
        pass
    return stroke


def _extract_line_strokes(symbol, sym_opacity) -> list:
    """All enabled stroke layers of a line symbol, bottom→top, as web strokes.
    Simple lines become solid/dashed strokes; marker/hashed lines become
    'tick' strokes."""
    strokes = []
    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)
        if not _sl_enabled(sl):
            continue
        if isinstance(sl, QgsSimpleLineSymbolLayer):
            strokes.append(_simple_line_stroke(sl, sym_opacity))
        elif ((_QgsMarkerLine and isinstance(sl, _QgsMarkerLine)) or
              (_QgsHashedLine and isinstance(sl, _QgsHashedLine))):
            ts = _templated_line_stroke(sl, sym_opacity)
            if ts:
                strokes.append(ts)
    return strokes


def _extract_line_symbol_style(symbol, sym_opacity) -> dict:
    """Line symbol → web style. Emits the top (core) stroke as flat fields for
    the swatch/fallback, plus a full strokes[] list (bottom→top) whenever the
    line has casing or tick layers so the web app can stack them faithfully."""
    strokes = _extract_line_strokes(symbol, sym_opacity)
    style = {"fillOpacity": 0}
    core = next((s for s in reversed(strokes) if not s.get("tick")), None)
    if core is None and strokes:
        core = strokes[-1]
    if core:
        style["color"]   = core["color"]
        style["opacity"] = core.get("opacity", 1)
        style["weight"]  = core.get("weight", 2)
        if core.get("dashArray"):
            style["dashArray"] = core["dashArray"]
    else:
        c = symbol.color()
        style["color"]   = _color_to_hex(c)
        style["opacity"] = round(c.alphaF(), 3)
        style["weight"]  = 2
    if len(strokes) > 1 or any(s.get("tick") for s in strokes):
        style["strokes"] = strokes
    return style


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

    # Line symbols: walk ALL layers so cased lines (casing + core) and
    # marker/hashed lines survive — handled by a dedicated extractor.
    if geom_type == QgsSymbol.Line:
        return _extract_line_symbol_style(symbol, sym_opacity)

    # Fill symbols need a multi-layer walk (fill + separate outline layers,
    # hatch brushes, pattern fills) — handled by a dedicated extractor.
    if geom_type == QgsSymbol.Fill:
        return _extract_fill_symbol_style(symbol, sym_opacity)

    # Walk symbol layers to find the primary marker paint layer
    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)

        if isinstance(sl, QgsSimpleMarkerSymbolLayer):
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

    if geom_type == QgsSymbol.Marker and "markerColor" not in style:
        c = symbol.color()
        style["markerColor"] = _color_to_hex(c)
        style["markerOpacity"] = round(c.alphaF(), 3)
        style["markerSize"] = 8

    # Hybrid: render the full marker symbol to a vector SVG so multi-layer
    # symbols, SVG/font markers and effects reproduce exactly as in QGIS.
    # The primitive marker* fields above remain as a client-side fallback.
    if geom_type == QgsSymbol.Marker:
        svg_marker = _render_marker_symbol_to_svg(symbol)
        if svg_marker:
            style["markerSvg"] = svg_marker

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
