"""
Unit tests for the intermap exporter package — run against the REAL code
(imported through tests/qgis_mock), not copies of it.

Run with:  python3 -m unittest discover tests -v
       or: python3 tests/test_exporter.py
"""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "qgis_mock"))
sys.path.insert(0, os.path.dirname(_HERE))

from qgis.PyQt.QtCore import Qt          # noqa: E402  (mock)
from qgis.PyQt.QtGui import QColor       # noqa: E402  (mock)
from qgis.core import QgsUnitTypes       # noqa: E402  (mock)

from intermap.exporter.assets import _script_safe_js                    # noqa: E402
from intermap.exporter.geometry import _flatten_coords                  # noqa: E402
from intermap.exporter.markers import (                                 # noqa: E402
    _SHAPE_ALIASES, _svg_inner, _uniquify_svg_ids,
)
from intermap.exporter.rasters import _dem_grid_size, _dem_quantize     # noqa: E402
from intermap.exporter.report import (                                  # noqa: E402
    _parse_front_matter, _report_image_refs, _validate_report_refs,
)
from intermap.exporter.styles import (                                  # noqa: E402
    _blend_hex, _pen_style_dash, _snap_hatch_angle, _extract_symbol_style,
)
from qgis.core import (                                                 # noqa: E402
    QgsSymbol, QgsSimpleLineSymbolLayer, QgsMarkerLineSymbolLayer,
)
from intermap.exporter.template import render_page, _page_template      # noqa: E402
from intermap.exporter.themes import _THEMES                            # noqa: E402
from intermap.exporter.utils import (                                   # noqa: E402
    _color_to_hex, _color_to_rgba, _richtext_body, _size_to_px,
)

import render_snapshot  # noqa: E402  (sibling test helper)


class ColorTests(unittest.TestCase):
    def test_color_to_hex(self):
        self.assertEqual(_color_to_hex(QColor(255, 128, 0)), "#ff8000")

    def test_color_to_hex_black(self):
        self.assertEqual(_color_to_hex(QColor(0, 0, 0)), "#000000")

    def test_color_to_rgba(self):
        self.assertEqual(_color_to_rgba(QColor(255, 0, 0, 128)),
                         "rgba(255,0,0,0.502)")


class RichTextTests(unittest.TestCase):
    def test_extracts_body_and_strips_p_styles(self):
        html = ('<html><head></head><body>'
                '<p style="margin:12px">Hello <b>world</b></p></body></html>')
        self.assertEqual(_richtext_body(html), "<p>Hello <b>world</b></p>")

    def test_plain_text_is_escaped(self):
        self.assertEqual(_richtext_body("a < b & c"), "a &lt; b &amp; c")


class UnitTests(unittest.TestCase):
    def test_pixels_pass_through(self):
        self.assertEqual(_size_to_px(10, QgsUnitTypes.RenderPixels), 10)

    def test_millimeters(self):
        self.assertAlmostEqual(_size_to_px(2, QgsUnitTypes.RenderMillimeters),
                               2 * 96.0 / 25.4)

    def test_points(self):
        self.assertAlmostEqual(_size_to_px(12, QgsUnitTypes.RenderPoints),
                               12 * 96.0 / 72.0)

    def test_unknown_unit_assumes_millimeters(self):
        self.assertAlmostEqual(_size_to_px(2, "no-such-unit"), 2 * 96.0 / 25.4)


class FlattenCoordsTests(unittest.TestCase):
    def test_point(self):
        geom = {"type": "Point", "coordinates": [10.0, 20.0]}
        self.assertEqual(list(_flatten_coords(geom)), [[10.0, 20.0]])

    def test_linestring(self):
        geom = {"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 2]]}
        self.assertEqual(len(list(_flatten_coords(geom))), 3)

    def test_polygon(self):
        geom = {"type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        self.assertEqual(len(list(_flatten_coords(geom))), 5)

    def test_multipolygon(self):
        geom = {"type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]],
                                [[[5, 5], [6, 5], [6, 6], [5, 5]]]]}
        self.assertEqual(len(list(_flatten_coords(geom))), 8)

    def test_geometry_collection(self):
        geom = {"type": "GeometryCollection", "geometries": [
            {"type": "Point", "coordinates": [1, 2]},
            {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        ]}
        self.assertEqual(len(list(_flatten_coords(geom))), 3)

    def test_empty(self):
        self.assertEqual(list(_flatten_coords({})), [])


class ShapeAliasTests(unittest.TestCase):
    def test_known_aliases(self):
        self.assertEqual(_SHAPE_ALIASES["rectangle"], "square")
        self.assertEqual(_SHAPE_ALIASES["equilateral_triangle"], "triangle")
        self.assertEqual(_SHAPE_ALIASES["cross2"], "x")

    def test_alias_targets_are_drawable(self):
        drawable = {"circle", "square", "diamond", "triangle", "pentagon",
                    "hexagon", "octagon", "star", "cross", "x"}
        self.assertTrue(set(_SHAPE_ALIASES.values()) <= drawable)


class SvgHelperTests(unittest.TestCase):
    def test_svg_inner_extracts_body(self):
        svg = '<svg width="10" height="10"><circle r="4"/></svg>'
        self.assertEqual(_svg_inner(svg), '<circle r="4"/>')

    def test_svg_inner_bad_input_returns_empty(self):
        self.assertEqual(_svg_inner("not svg at all"), "")

    def test_uniquify_namespaces_ids_and_refs(self):
        inner = '<linearGradient id="g1"/><rect fill="url(#g1)"/>'
        out = _uniquify_svg_ids(inner)
        self.assertNotIn('id="g1"', out)
        self.assertIn("url(#", out)
        # id and reference still agree
        import re
        gid = re.search(r'id="([^"]+)"', out).group(1)
        self.assertIn('url(#%s)' % gid, out)

    def test_uniquify_distinct_per_call(self):
        inner = '<clipPath id="c"/>'
        self.assertNotEqual(_uniquify_svg_ids(inner), _uniquify_svg_ids(inner))

    def test_uniquify_noop_without_ids(self):
        self.assertEqual(_uniquify_svg_ids("<rect/>"), "<rect/>")


class StyleHelperTests(unittest.TestCase):
    def test_pen_style_dash(self):
        self.assertEqual(_pen_style_dash(Qt.PenStyle.DashLine), "8 4")
        self.assertEqual(_pen_style_dash(Qt.PenStyle.DotLine), "2 4")
        self.assertEqual(_pen_style_dash(Qt.PenStyle.DashDotLine), "8 4 2 4")
        self.assertEqual(_pen_style_dash(Qt.PenStyle.DashDotDotLine), "8 4 2 4 2 4")
        self.assertIsNone(_pen_style_dash(Qt.PenStyle.SolidLine))

    def test_snap_hatch_angle_cardinals(self):
        self.assertEqual(_snap_hatch_angle(0), "hor")
        self.assertEqual(_snap_hatch_angle(90), "ver")
        self.assertEqual(_snap_hatch_angle(45), "bdiag")
        self.assertEqual(_snap_hatch_angle(135), "fdiag")

    def test_snap_hatch_angle_wraps_and_rounds(self):
        self.assertEqual(_snap_hatch_angle(180), "hor")
        self.assertEqual(_snap_hatch_angle(184), "hor")
        self.assertEqual(_snap_hatch_angle(268), "ver")

    def test_blend_hex_midpoint(self):
        self.assertEqual(_blend_hex(QColor(0, 0, 0), QColor(255, 255, 255)),
                         "#7f7f7f")


class DemTests(unittest.TestCase):
    def test_grid_size_square(self):
        self.assertEqual(_dem_grid_size(1.0, 1.0), (512, 512))

    def test_grid_size_wide(self):
        gw, gh = _dem_grid_size(2.0, 1.0)
        self.assertEqual(gw, 512)
        self.assertEqual(gh, 256)

    def test_grid_size_tall(self):
        gw, gh = _dem_grid_size(1.0, 4.0)
        self.assertEqual(gh, 512)
        self.assertEqual(gw, 128)

    def test_grid_size_degenerate_extent(self):
        gw, gh = _dem_grid_size(0.0, 0.0)
        self.assertGreaterEqual(gw, 2)
        self.assertGreaterEqual(gh, 2)

    def test_grid_size_extreme_aspect_clamps_to_two(self):
        gw, gh = _dem_grid_size(10000.0, 0.0001)
        self.assertGreaterEqual(gh, 2)

    def test_quantize_round_trip(self):
        rows = [[0.0, 50.0], [100.0, 25.0]]
        vmin, vmax, data = _dem_quantize(rows)
        self.assertEqual((vmin, vmax), (0.0, 100.0))
        vals = [int.from_bytes(data[i:i + 2], "little")
                for i in range(0, len(data), 2)]
        decoded = [vmin + v / 65535.0 * (vmax - vmin) for v in vals]
        for got, want in zip(decoded, [0.0, 50.0, 100.0, 25.0]):
            self.assertAlmostEqual(got, want, places=2)

    def test_quantize_nodata_encodes_as_minimum(self):
        rows = [[10.0, None], [30.0, 20.0]]
        vmin, _vmax, data = _dem_quantize(rows)
        self.assertEqual(vmin, 10.0)
        self.assertEqual(int.from_bytes(data[2:4], "little"), 0)

    def test_quantize_all_nodata(self):
        vmin, vmax, data = _dem_quantize([[None, None]])
        self.assertEqual((vmin, vmax), (0.0, 0.0))
        self.assertEqual(data, b"\x00\x00\x00\x00")

    def test_quantize_flat_grid_no_divide_by_zero(self):
        vmin, vmax, data = _dem_quantize([[5.0, 5.0]])
        self.assertEqual(vmin, 5.0)
        self.assertEqual(len(data), 4)


class FrontMatterTests(unittest.TestCase):
    def test_title_and_autolink(self):
        meta, body = _parse_front_matter(
            "---\ntitle: My Report\nautolink:\n"
            "  - layer: Boreholes\n    field: name\n    pattern: BH\\d+\n"
            "---\n# Heading\n")
        self.assertEqual(meta.get("title"), "My Report")
        self.assertEqual(meta["autolink"][0]["layer"], "Boreholes")
        self.assertTrue(body.startswith("# Heading"))

    def test_absent(self):
        meta, body = _parse_front_matter("# Just markdown\n")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# Just markdown\n")

    def test_unterminated_is_ignored(self):
        meta, body = _parse_front_matter("---\ntitle: x\nno end")
        self.assertEqual(meta, {})
        self.assertTrue(body.startswith("---"))


class ReportRefTests(unittest.TestCase):
    def test_image_refs_unique_in_order(self):
        md = "![a](one.png)\n![b](two.png)\n![c](one.png)\n"
        self.assertEqual(_report_image_refs(md), ["one.png", "two.png"])

    def test_validate_flags_dead_links(self):
        md = ("[v](view:Nope)\n[g](gis:Ghost?f=1)\n"
              ":::view AlsoMissing\n")
        warnings = _validate_report_refs(md, {}, ["RealLayer"], ["RealView"])
        joined = "\n".join(warnings)
        self.assertIn("Nope", joined)
        self.assertIn("Ghost", joined)
        self.assertIn("AlsoMissing", joined)

    def test_validate_accepts_good_refs(self):
        md = "[v](view:RealView)\n[g](gis:RealLayer?f=1)\n"
        self.assertEqual(
            _validate_report_refs(md, {}, ["RealLayer"], ["RealView"]), [])


class PdfReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_test_pdf import make_pdf
        cls.tmp = tempfile.mkdtemp(prefix="intermap-pdf-")
        cls.pdf_path = os.path.join(cls.tmp, "site report.pdf")
        with open(cls.pdf_path, "wb") as f:
            f.write(make_pdf(3))

    def _build(self, bindings, views=("Overview", "North detail")):
        from intermap.exporter.report import _build_pdf_report_payload
        return _build_pdf_report_payload(self.pdf_path, bindings, list(views))

    def test_payload_shape(self):
        import base64
        p = self._build([{"page": 2, "view": "Overview"}])
        self.assertEqual(p["title"], "site report")
        self.assertEqual(p["pages"], 3)
        self.assertEqual(p["bindings"], [{"page": 2, "view": "Overview"}])
        self.assertEqual(p["warnings"], [])
        raw = base64.b64decode(p["pdf"])
        self.assertTrue(raw.startswith(b"%PDF-"))

    def test_bindings_sorted_by_page(self):
        p = self._build([{"page": 3, "view": "Overview"},
                         {"page": 1, "view": "North detail"}])
        self.assertEqual([b["page"] for b in p["bindings"]], [1, 3])

    def test_unknown_view_warned_but_kept(self):
        p = self._build([{"page": 1, "view": "Nope"}])
        self.assertTrue(any("Nope" in w for w in p["warnings"]))
        self.assertEqual(len(p["bindings"]), 1)

    def test_out_of_range_page_warned(self):
        p = self._build([{"page": 7, "view": "Overview"}])
        self.assertTrue(any("beyond last page" in w for w in p["warnings"]))

    def test_invalid_page_dropped(self):
        p = self._build([{"page": "x", "view": "Overview"},
                         {"page": 0, "view": "Overview"},
                         {"view": "Overview"}])
        self.assertEqual(p["bindings"], [])
        self.assertEqual(len(p["warnings"]), 3)

    def test_empty_view_dropped_silently(self):
        p = self._build([{"page": 1, "view": "  "}])
        self.assertEqual(p["bindings"], [])
        self.assertEqual(p["warnings"], [])

    def test_page_count_regex_ignores_pages_tree(self):
        from intermap.exporter.report import _pdf_page_count
        self.assertEqual(
            _pdf_page_count(b"<< /Type /Pages >> << /Type /Page >>"), 1)

    def test_view_opts_parsing(self):
        from intermap.exporter.report import _parse_view_opts
        self.assertEqual(_parse_view_opts("3d pitch=-35 heading=120"),
                         {"mode3d": True, "pitch": -35.0, "heading": 120.0})
        self.assertEqual(_parse_view_opts(""), {})
        self.assertEqual(_parse_view_opts("pitch=abc junk"), {})

    def test_binding_opts_passed_through(self):
        p = self._build([{"page": 2, "view": "Overview",
                          "opts": "3d pitch=-30"}])
        self.assertEqual(p["bindings"][0]["opts"],
                         {"mode3d": True, "pitch": -30.0})

    def test_binding_without_opts_has_no_opts_key(self):
        p = self._build([{"page": 2, "view": "Overview", "opts": "  "}])
        self.assertNotIn("opts", p["bindings"][0])


class _FakeSimpleLine(QgsSimpleLineSymbolLayer):
    def __init__(self, color, width_mm, pen="solid"):
        self._c, self._w, self._pen = color, width_mm, pen

    def enabled(self): return True
    def color(self): return self._c
    def width(self): return self._w
    def widthUnit(self): return QgsUnitTypes.RenderMillimeters
    def penStyle(self): return {"solid": Qt.PenStyle.SolidLine, "dash": Qt.PenStyle.DashLine}[self._pen]


class _FakeMarkerLine(QgsMarkerLineSymbolLayer):
    def __init__(self, sub_color, interval_mm=3.0, hash_len_mm=2.0):
        self._sub_color, self._iv, self._hl = sub_color, interval_mm, hash_len_mm

    def enabled(self): return True
    def color(self): return self._sub_color
    def subSymbol(self):
        outer = self
        class _Sub:
            def color(self): return outer._sub_color
            def symbolLayerCount(self): return 0
        return _Sub()
    def interval(self): return self._iv
    def intervalUnit(self): return QgsUnitTypes.RenderMillimeters
    def hashLength(self): return self._hl
    def hashLengthUnit(self): return QgsUnitTypes.RenderMillimeters


class _FakeSymbol:
    def __init__(self, geom_type, layers, opacity=1.0):
        self._t, self._layers, self._op = geom_type, layers, opacity

    def type(self): return self._t
    def opacity(self): return self._op
    def symbolLayerCount(self): return len(self._layers)
    def symbolLayer(self, i): return self._layers[i]
    def color(self): return QColor(0, 0, 0)


class LineSymbologyTests(unittest.TestCase):
    def test_single_line_no_strokes_list(self):
        sym = _FakeSymbol(QgsSymbol.Line,
                          [_FakeSimpleLine(QColor(255, 0, 0), 1.0)])
        style = _extract_symbol_style(sym)
        self.assertEqual(style["color"], "#ff0000")
        self.assertNotIn("strokes", style)          # single stroke stays flat
        self.assertEqual(style["fillOpacity"], 0)

    def test_cased_line_emits_stacked_strokes(self):
        # casing (wide blue, drawn first/bottom) + core (narrow yellow, top)
        sym = _FakeSymbol(QgsSymbol.Line, [
            _FakeSimpleLine(QColor(0, 0, 255), 3.0),   # casing
            _FakeSimpleLine(QColor(255, 255, 0), 1.0),  # core
        ])
        style = _extract_symbol_style(sym)
        self.assertIn("strokes", style)
        self.assertEqual(len(style["strokes"]), 2)
        # bottom→top order preserved
        self.assertEqual(style["strokes"][0]["color"], "#0000ff")
        self.assertEqual(style["strokes"][1]["color"], "#ffff00")
        self.assertGreater(style["strokes"][0]["weight"], style["strokes"][1]["weight"])
        # flat fields describe the top (core) stroke for the legend swatch
        self.assertEqual(style["color"], "#ffff00")

    def test_dashed_line_stroke(self):
        sym = _FakeSymbol(QgsSymbol.Line,
                          [_FakeSimpleLine(QColor(0, 0, 0), 1.0, pen="dash"),
                           _FakeSimpleLine(QColor(0, 0, 0), 1.0)])
        style = _extract_symbol_style(sym)
        self.assertEqual(style["strokes"][0].get("dashArray"), "8 4")

    def test_marker_line_becomes_tick_stroke(self):
        sym = _FakeSymbol(QgsSymbol.Line, [
            _FakeSimpleLine(QColor(160, 32, 240), 0.5),   # thin base line
            _FakeMarkerLine(QColor(160, 32, 240)),         # ticks
        ])
        style = _extract_symbol_style(sym)
        self.assertIn("strokes", style)
        ticks = [s for s in style["strokes"] if s.get("tick")]
        self.assertEqual(len(ticks), 1)
        self.assertEqual(ticks[0]["color"], "#a020f0")
        self.assertGreater(ticks[0]["interval"], 0)
        self.assertGreater(ticks[0]["tickLen"], 0)


class ScriptSafeJsTests(unittest.TestCase):
    def test_escapes_close_script_tag(self):
        self.assertEqual(_script_safe_js('a="</script>"'), 'a="<\\/script>"')

    def test_case_insensitive(self):
        self.assertEqual(_script_safe_js("</SCRIPT>"), "<\\/SCRIPT>")

    def test_leaves_regex_literals_alone(self):
        js = "if (/^</.test(x)) { y('</div>'); }"
        self.assertEqual(_script_safe_js(js), js)


class TemplateTests(unittest.TestCase):
    def test_all_placeholders_resolved_by_render(self):
        import re
        fields = set(re.findall(r"@@([A-Za-z_][A-Za-z0-9_]*)@@",
                                _page_template()))
        self.assertTrue(fields, "template should declare placeholders")
        ctx = {f: "X" for f in fields}
        out = render_page(ctx)
        self.assertNotIn("@@", out)

    def test_missing_context_key_raises(self):
        with self.assertRaises(KeyError):
            render_page({})

    def test_value_containing_placeholder_not_reprocessed(self):
        import re
        fields = set(re.findall(r"@@([A-Za-z_][A-Za-z0-9_]*)@@",
                                _page_template()))
        ctx = {f: "@@layers_json@@" for f in fields}
        out = render_page(ctx)
        # values are inserted literally, never substituted again
        self.assertIn("@@layers_json@@", out)


class ThemeTests(unittest.TestCase):
    def test_all_themes_define_all_tokens(self):
        keys = set(_THEMES["corporate"].keys())
        for name, theme in _THEMES.items():
            self.assertEqual(set(theme.keys()), keys,
                             "theme %s token mismatch" % name)


class RenderedPageTests(unittest.TestCase):
    """End-to-end: build the page like export() does and inspect the result."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="intermap-test-")
        cls.layer_defs = render_snapshot.build_layer_defs()
        cls.bounds = [[51.4, -0.2], [51.6, 0.0]]
        cls.pages = {
            name: exporter._render_html(cls.layer_defs, cls.bounds)
            for name, exporter in render_snapshot.build_scenarios(cls.tmp).items()
        }

    def test_no_unresolved_placeholders(self):
        # Match the substitution pattern, not bare '@@' — embedded libraries
        # may legitimately contain '@@' (e.g. pdf.js's "@@iterator" string).
        import re
        pat = re.compile(r"@@[A-Za-z_][A-Za-z0-9_]*@@")
        for name, html in self.pages.items():
            self.assertIsNone(pat.search(html), name)

    def _layers_payload(self, scenario="full"):
        html = self.pages[scenario]
        marker = "var LAYERS = "
        start = html.index(marker) + len(marker)
        end = html.index(";\n", start)
        return json.loads(html[start:end].replace("<\\/", "</"))

    def test_layers_payload_embeds_and_parses(self):
        payload = self._layers_payload()
        self.assertEqual([ld["name"] for ld in payload],
                         [ld["name"] for ld in self.layer_defs])

    def test_line_strokes_survive_to_payload(self):
        by_name = {ld["name"]: ld for ld in self._layers_payload()}
        routes = by_name["Routes"]["styleMap"]["style"]
        self.assertEqual(len(routes["strokes"]), 2)   # casing + core
        ticks = by_name["Boundary ticks"]["styleMap"]["style"]["strokes"]
        self.assertTrue(any(s.get("tick") for s in ticks))

    def test_line_deco_overlay_present(self):
        # the container the curved labels / ticks render into
        self.assertIn('id="line-deco-svg"', self.pages["full"])

    def test_report_pane_has_pdf_and_thumbnail_controls(self):
        html = self.pages["report"]
        self.assertIn('id="report-pdf"', html)       # PDF export button
        self.assertIn('id="report-thumbs"', html)    # thumbnail strip
        self.assertIn('id="report-collapse"', html)  # collapse to thumbnails
        self.assertIn('id="report-expand"', html)

    def test_report_scenario_embeds_marked_and_payload(self):
        html = self.pages["report"]
        self.assertIn("REPORT", html)
        self.assertIn("marked", html)
        # the fix: no corrupted regex from blanket </ escaping
        self.assertNotIn("/^<\\/.test", html)

    def test_minimal_scenario_disables_features(self):
        html = self.pages["minimal"]
        start = html.index("var FEAT = ") + len("var FEAT = ")
        feat = json.loads(html[start:html.index(";\n", start)])
        self.assertFalse(any(feat.values()),
                         "all features should be off: %s" % feat)

    def test_full_scenario_enables_features(self):
        html = self.pages["full"]
        start = html.index("var FEAT = ") + len("var FEAT = ")
        feat = json.loads(html[start:html.index(";\n", start)])
        self.assertTrue(all(v for k, v in feat.items()))

    def test_page_ends_cleanly(self):
        for name, html in self.pages.items():
            self.assertTrue(html.startswith("<!DOCTYPE html>"), name)
            self.assertTrue(html.endswith("</html>"), name)

    def test_script_blocks_balanced(self):
        import re
        for name, html in self.pages.items():
            opens = len(re.findall(r"<script(?:\s[^>]*)?>", html))
            closes = html.count("</script>")
            self.assertEqual(opens, closes, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
