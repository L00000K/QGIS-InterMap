"""
Offline unit tests for parts of exporter.py that don't require QGIS.
Run with: python3 -m pytest qgis_webmap/test_exporter_logic.py -v
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Mock the QGIS namespace so we can import exporter without QGIS installed ──
class _FakeColor:
    def __init__(self, r, g, b, a=255):
        self._r, self._g, self._b, self._a = r, g, b, a
    def red(self): return self._r
    def green(self): return self._g
    def blue(self): return self._b
    def alphaF(self): return self._a / 255.0


def _color_to_hex(color):
    return "#{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue())


def _color_to_rgba(color):
    return "rgba({},{},{},{:.3f})".format(
        color.red(), color.green(), color.blue(), color.alphaF()
    )


def _flatten_coords(geom):
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


# ── SVG symbol helpers (mirrors exporter.py, no QGIS needed) ─────────────────
_svg_id_counter = [0]


def _reset_svg_counter():
    _svg_id_counter[0] = 0


def _svg_inner(svg_text):
    try:
        lt = svg_text.index("<svg")
        gt = svg_text.index(">", lt) + 1
        end = svg_text.rindex("</svg>")
        return svg_text[gt:end].strip()
    except Exception:
        return ""


def _uniquify_svg_ids(inner):
    import re
    ids = set(re.findall(r'id="([^"]+)"', inner))
    if not ids:
        return inner
    _svg_id_counter[0] += 1
    prefix = "s%d_" % _svg_id_counter[0]
    for i in sorted(ids, key=len, reverse=True):
        inner = inner.replace('id="%s"' % i, 'id="%s%s"' % (prefix, i))
        inner = inner.replace('url(#%s)' % i, 'url(#%s%s)' % (prefix, i))
        inner = inner.replace('"#%s"' % i, '"#%s%s"' % (prefix, i))
        inner = inner.replace("'#%s'" % i, "'#%s%s'" % (prefix, i))
    return inner


# ── Tests ──────────────────────────────────────────────────────────────────

def test_color_to_hex():
    c = _FakeColor(255, 128, 0)
    assert _color_to_hex(c) == "#ff8000"


def test_color_to_hex_black():
    c = _FakeColor(0, 0, 0)
    assert _color_to_hex(c) == "#000000"


def test_flatten_point():
    geom = {"type": "Point", "coordinates": [10.0, 20.0]}
    coords = list(_flatten_coords(geom))
    assert coords == [[10.0, 20.0]]


def test_flatten_linestring():
    geom = {"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 2]]}
    coords = list(_flatten_coords(geom))
    assert len(coords) == 3


def test_flatten_polygon():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    coords = list(_flatten_coords(geom))
    assert len(coords) == 5


def test_flatten_multipolygon():
    geom = {
        "type": "MultiPolygon",
        "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]],
                        [[[2, 2], [3, 2], [3, 3], [2, 2]]]]
    }
    coords = list(_flatten_coords(geom))
    assert len(coords) == 8


def test_flatten_empty():
    geom = {"type": "Point", "coordinates": []}
    coords = list(_flatten_coords(geom))
    assert coords == []


def test_geojson_structure():
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
         "properties": {"name": "test"}}
    ]}
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    assert fc["features"][0]["properties"]["name"] == "test"


def test_style_map_json_serialisable():
    style_map = {
        "type": "categorized",
        "field": "category",
        "entries": [
            {"value": "A", "label": "Type A", "style": {"fillColor": "#ff0000", "fillOpacity": 0.8, "color": "#000", "weight": 1, "opacity": 1}},
            {"value": "B", "label": "Type B", "style": {"fillColor": "#0000ff", "fillOpacity": 0.8, "color": "#000", "weight": 1, "opacity": 1}},
        ],
        "default": {},
    }
    dumped = json.dumps(style_map)
    loaded = json.loads(dumped)
    assert loaded["type"] == "categorized"
    assert loaded["entries"][0]["style"]["fillColor"] == "#ff0000"
    assert loaded["entries"][0]["label"] == "Type A"


def test_graduated_style_map():
    style_map = {
        "type": "graduated",
        "field": "value",
        "entries": [
            {"min": 0.0, "max": 10.0, "label": "0 – 10", "style": {"fillColor": "#ffffcc"}},
            {"min": 10.0, "max": 20.0, "label": "10 – 20", "style": {"fillColor": "#fd8d3c"}},
        ],
        "default": {},
    }
    dumped = json.dumps(style_map)
    loaded = json.loads(dumped)
    assert loaded["entries"][1]["min"] == 10.0
    assert loaded["entries"][1]["label"] == "10 – 20"


def test_html_contains_leaflet():
    # Simulate a minimal render
    layer_defs = [{
        "kind": "vector",
        "name": "Test Layer",
        "geomType": "point",
        "geojson": {"type": "FeatureCollection", "features": []},
        "styleMap": {"type": "single", "style": {"markerColor": "#ff0000", "markerSize": 8}},
    }]
    bounds = [[51.4, -0.2], [51.6, 0.0]]
    layers_json = json.dumps(layer_defs, separators=(",", ":"))
    bounds_json = json.dumps(bounds)
    html = f"<script src='leaflet.js'></script><div id='map'></div><script>var LAYERS={layers_json}; var bounds={bounds_json};</script>"
    assert "leaflet" in html.lower()
    assert "LAYERS" in html
    assert "Test Layer" in html


# ── Marker shape + size conversion (mirrors exporter helpers) ─────────────────

class _RenderUnit:
    RenderMillimeters = 0
    RenderMapUnits = 1
    RenderPixels = 2
    RenderPercentage = 3
    RenderPoints = 4
    RenderInches = 5


def _size_to_px(size, unit):
    if unit == _RenderUnit.RenderPixels:
        return size
    if unit == _RenderUnit.RenderPoints:
        return size * 96.0 / 72.0
    if unit == _RenderUnit.RenderInches:
        return size * 96.0
    return size * 96.0 / 25.4  # millimeters / default


_SHAPE_ALIASES = {
    "square": "square", "rectangle": "square", "square_with_corners": "square",
    "rounded_square": "square", "diamond": "diamond", "triangle": "triangle",
    "equilateral_triangle": "triangle", "star": "star", "regular_star": "star",
    "pentagon": "pentagon", "hexagon": "hexagon", "octagon": "octagon",
    "cross": "cross", "cross2": "x", "x": "x", "cross_fill": "square",
    "circle": "circle",
}


def _alias(raw):
    return _SHAPE_ALIASES.get(str(raw).lower(), "circle")


def test_size_to_px_pixels():
    assert _size_to_px(10, _RenderUnit.RenderPixels) == 10


def test_size_to_px_millimeters():
    # 2mm at 96 DPI ≈ 7.56 px
    px = _size_to_px(2.0, _RenderUnit.RenderMillimeters)
    assert 7.0 < px < 8.0


def test_size_to_px_points():
    # 72 points == 1 inch == 96 px
    assert abs(_size_to_px(72, _RenderUnit.RenderPoints) - 96.0) < 0.001


def test_shape_alias_known():
    assert _alias("equilateral_triangle") == "triangle"
    assert _alias("Square") == "square"
    assert _alias("regular_star") == "star"


def test_shape_alias_unknown_falls_back_to_circle():
    assert _alias("some_exotic_shape") == "circle"


def test_marker_style_serialisable_with_shape():
    style = {
        "markerColor": "#ff0000", "markerOpacity": 0.9,
        "markerStrokeColor": "#000000", "markerStrokeWidth": 1.0,
        "markerSize": 12, "markerShape": "star", "markerAngle": 45,
    }
    loaded = json.loads(json.dumps(style))
    assert loaded["markerShape"] == "star"
    assert loaded["markerSize"] == 12


def test_svg_inner_extracts_body():
    svg = ('<?xml version="1.0"?>\n<!DOCTYPE svg>\n'
           '<svg width="10" height="10"><g><circle r="3"/></g></svg>\n')
    assert _svg_inner(svg) == '<g><circle r="3"/></g>'


def test_svg_inner_bad_input_returns_empty():
    assert _svg_inner("not svg at all") == ""


def test_uniquify_svg_ids_namespaces_refs():
    _reset_svg_counter()
    inner = '<clipPath id="clip0"><rect/></clipPath><path clip-path="url(#clip0)"/>'
    out = _uniquify_svg_ids(inner)
    assert 'id="s1_clip0"' in out
    assert 'url(#s1_clip0)' in out
    assert 'url(#clip0)' not in out


def test_uniquify_svg_ids_distinct_per_call():
    _reset_svg_counter()
    a = _uniquify_svg_ids('<g id="g0"/>')
    b = _uniquify_svg_ids('<g id="g0"/>')
    assert 'id="s1_g0"' in a
    assert 'id="s2_g0"' in b


def test_uniquify_svg_ids_noop_without_ids():
    inner = '<circle r="3"/>'
    assert _uniquify_svg_ids(inner) == inner


def test_marker_svg_payload_serialisable():
    style = {
        "markerColor": "#ff0000", "markerSize": 12, "markerShape": "circle",
        "markerSvg": {"w": 18.0, "h": 20.0, "ax": 9.0, "ay": 10.0,
                      "inner": '<g><circle r="3" fill="#f00"/></g>'},
    }
    loaded = json.loads(json.dumps(style))
    assert loaded["markerSvg"]["w"] == 18.0
    assert "circle" in loaded["markerSvg"]["inner"]


# ── Fill symbology helpers (mirrors exporter.py, no QGIS needed) ─────────────

def _snap_hatch_angle(angle):
    a = float(angle) % 180.0
    if a < 22.5 or a >= 157.5:
        return "hor"
    if a < 67.5:
        return "bdiag"
    if a < 112.5:
        return "ver"
    return "fdiag"


class _Pen:
    NoPen, SolidLine, DashLine, DotLine, DashDotLine, DashDotDotLine = range(6)


def _pen_style_dash(pen):
    if pen == _Pen.DashLine:
        return "8 4"
    if pen == _Pen.DotLine:
        return "2 4"
    if pen == _Pen.DashDotLine:
        return "8 4 2 4"
    if pen == _Pen.DashDotDotLine:
        return "8 4 2 4 2 4"
    return None


def _blend_hex_rgb(r1, g1, b1, r2, g2, b2):
    return "#{:02x}{:02x}{:02x}".format((r1 + r2) // 2, (g1 + g2) // 2, (b1 + b2) // 2)


def test_snap_hatch_angle_cardinals():
    assert _snap_hatch_angle(0) == "hor"
    assert _snap_hatch_angle(45) == "bdiag"
    assert _snap_hatch_angle(90) == "ver"
    assert _snap_hatch_angle(135) == "fdiag"


def test_snap_hatch_angle_wraps_and_rounds():
    assert _snap_hatch_angle(180) == "hor"
    assert _snap_hatch_angle(170) == "hor"
    assert _snap_hatch_angle(225) == "bdiag"   # 225 % 180 = 45
    assert _snap_hatch_angle(100) == "ver"
    assert _snap_hatch_angle(-45) == "fdiag"   # -45 % 180 = 135


def test_pen_style_dash():
    assert _pen_style_dash(_Pen.DashLine) == "8 4"
    assert _pen_style_dash(_Pen.DotLine) == "2 4"
    assert _pen_style_dash(_Pen.SolidLine) is None
    assert _pen_style_dash(_Pen.NoPen) is None


def test_blend_hex_midpoint():
    assert _blend_hex_rgb(0, 0, 0, 255, 255, 255) == "#7f7f7f"
    assert _blend_hex_rgb(255, 0, 0, 0, 0, 255) == "#7f007f"


def test_fill_hatch_style_serialisable():
    style = {
        "fillHatch": {"kind": "bdiag", "color": "#ff0000", "opacity": 0.8,
                      "width": 1.5, "spacing": 6.0},
        "color": "#000000", "weight": 1.5, "opacity": 1, "dashArray": "8 4",
    }
    loaded = json.loads(json.dumps(style))
    assert loaded["fillHatch"]["kind"] == "bdiag"
    assert loaded["fillHatch"]["spacing"] == 6.0
    assert loaded["dashArray"] == "8 4"


def test_outline_only_polygon_style():
    # No-brush fill with a stroke: fill must be fully transparent
    style = {"fillOpacity": 0, "color": "#222222", "weight": 2, "opacity": 1}
    loaded = json.loads(json.dumps(style))
    assert loaded["fillOpacity"] == 0
    assert loaded["weight"] == 2


def test_wms_layer_def_serialisable():
    ld = {
        "kind": "wms", "name": "WMS", "bounds": [[0, 0], [1, 1]],
        "wmsUrl": "https://example.com/wms", "wmsLayers": "l1",
        "wmsFormat": "image/png", "wmsStyles": "", "wmsCrs": "EPSG:3857",
        "wmsVersion": "1.3.0", "tileType": "wms",
    }
    loaded = json.loads(json.dumps(ld))
    assert loaded["kind"] == "wms"
    assert loaded["wmsUrl"].startswith("https://")


# ── DEM helpers — real functions extracted from exporter.py via AST ──────────
# (exporter.py imports qgis at module level, so it can't be imported here;
# these helpers are pure Python, so pull just their definitions and exec them)

import ast as _ast
import base64 as _base64
import struct as _struct


def _load_exporter_functions(*names):
    import re as _re
    src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exporter.py")
    with open(src_path, encoding="utf-8") as f:
        tree = _ast.parse(f.read())
    ns = {"base64": _base64, "re": _re, "os": os, "Optional": None}
    found = set()
    for node in tree.body:
        name = None
        if isinstance(node, _ast.FunctionDef) and node.name in names:
            name = node.name
        elif (isinstance(node, _ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], _ast.Name)
              and node.targets[0].id in names):
            name = node.targets[0].id
        if name:
            exec(compile(_ast.Module(body=[node], type_ignores=[]), src_path, "exec"), ns)
            found.add(name)
    missing = set(names) - found
    assert not missing, f"not found in exporter.py: {missing}"
    return tuple(ns[n] for n in names)


_dem_grid_size, _dem_quantize = _load_exporter_functions("_dem_grid_size", "_dem_quantize")


def test_dem_grid_size_square():
    assert _dem_grid_size(1.0, 1.0, 512) == (512, 512)


def test_dem_grid_size_wide():
    gw, gh = _dem_grid_size(2.0, 1.0, 512)
    assert gw == 512 and gh == 256


def test_dem_grid_size_tall():
    gw, gh = _dem_grid_size(1.0, 2.0, 512)
    assert gw == 256 and gh == 512


def test_dem_grid_size_degenerate_extent():
    assert _dem_grid_size(0.0, 1.0) == (2, 2)
    assert _dem_grid_size(1.0, -5.0) == (2, 2)


def test_dem_grid_size_extreme_aspect_clamps_to_two():
    gw, gh = _dem_grid_size(1000.0, 1.0, 512)
    assert gw == 512 and gh == 2


def test_dem_quantize_round_trip():
    rows = [[100.0, 200.0], [300.0, 150.0]]
    vmin, vmax, raw = _dem_quantize(rows)
    assert (vmin, vmax) == (100.0, 300.0)
    assert len(raw) == 4 * 2  # u16 per cell, little-endian
    decoded = [vmin + q / 65535 * (vmax - vmin)
               for q in _struct.unpack("<4H", raw)]
    for got, want in zip(decoded, [100.0, 200.0, 300.0, 150.0]):
        assert abs(got - want) < (vmax - vmin) / 65535 + 1e-9


def test_dem_quantize_nodata_encodes_as_minimum():
    rows = [[50.0, None], [None, 250.0]]
    vmin, vmax, raw = _dem_quantize(rows)
    qs = _struct.unpack("<4H", raw)
    assert qs[1] == 0 and qs[2] == 0          # nodata → 0 → decodes to vmin
    assert vmin == 50.0 and vmax == 250.0


def test_dem_quantize_all_nodata():
    vmin, vmax, raw = _dem_quantize([[None, None], [None, None]])
    assert (vmin, vmax) == (0.0, 0.0)
    assert raw == b"\x00\x00" * 4


def test_dem_quantize_flat_grid_no_divide_by_zero():
    vmin, vmax, raw = _dem_quantize([[42.0, 42.0]])
    assert vmin == vmax == 42.0
    assert _struct.unpack("<2H", raw) == (0, 0)  # all values sit at the floor


# ── Report / story mode helpers ───────────────────────────────────────────────

(_parse_front_matter, _report_image_refs, _validate_report_refs,
 _REPORT_IMG_RE) = _load_exporter_functions(
    "_parse_front_matter", "_report_image_refs", "_validate_report_refs",
    "_REPORT_IMG_RE")


_FM_SAMPLE = """---
title: Site Investigation Report
autolink:
  - layer: Boreholes
    field: ID
    pattern: "BH-\\\\d+"
  - layer: Trial Pits
    field: Ref
    pattern: "TP\\\\d+"
---

# Introduction

Body text here.
"""


def test_front_matter_title_and_autolink():
    meta, body = _parse_front_matter(_FM_SAMPLE)
    assert meta["title"] == "Site Investigation Report"
    assert len(meta["autolink"]) == 2
    assert meta["autolink"][0] == {"layer": "Boreholes", "field": "ID", "pattern": "BH-\\\\d+"}
    assert body.startswith("\n# Introduction")


def test_front_matter_absent():
    meta, body = _parse_front_matter("# No front matter\n\ntext")
    assert meta == {} and body.startswith("# No front matter")


def test_front_matter_unterminated_is_ignored():
    text = "---\ntitle: broken\nno closing fence"
    meta, body = _parse_front_matter(text)
    assert meta == {} and body == text


def test_front_matter_incomplete_autolink_entries_dropped():
    meta, _ = _parse_front_matter(
        "---\nautolink:\n  - layer: L\n    field: F\n---\nbody")
    assert meta["autolink"] == []  # no pattern → dropped


def test_report_image_refs_unique_in_order():
    md = ("![a](figures/one.png) text ![b](figures/two.png)\n"
          "again ![c](figures/one.png) and ![d](https://x/y.png)")
    assert _report_image_refs(md) == [
        "figures/one.png", "figures/two.png", "https://x/y.png"]


def test_validate_report_refs_flags_dead_links():
    md = (":::view Missing View\n"
          "A [link](gis:NoLayer?ID=1) and [ok](gis:Boreholes?ID=2).\n"
          "[v](view:Site Overview)\n"
          ':::table layer="Ghost" {#tbl:x}\n')
    warnings = _validate_report_refs(
        md, {"autolink": [{"layer": "Boreholes", "field": "ID", "pattern": "x"}]},
        layer_names=["Boreholes"], view_names=["Site Overview"])
    joined = "\n".join(warnings)
    assert "Missing View" in joined
    assert "NoLayer" in joined
    assert "Ghost" in joined
    assert "Site Overview" not in joined and "Boreholes" not in joined


def test_validate_report_refs_strips_view_options():
    md = ":::view Site Overview [3d pitch=-35 heading=120]\n"
    warnings = _validate_report_refs(md, {"autolink": []},
                                     layer_names=[], view_names=["Site Overview"])
    assert warnings == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
