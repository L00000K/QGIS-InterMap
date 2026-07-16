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
    _blend_hex, _pen_style_dash, _snap_hatch_angle,
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
        self.assertEqual(_pen_style_dash(Qt.DashLine), "8 4")
        self.assertEqual(_pen_style_dash(Qt.DotLine), "2 4")
        self.assertEqual(_pen_style_dash(Qt.DashDotLine), "8 4 2 4")
        self.assertEqual(_pen_style_dash(Qt.DashDotDotLine), "8 4 2 4 2 4")
        self.assertIsNone(_pen_style_dash(Qt.SolidLine))

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
        for name, html in self.pages.items():
            self.assertNotIn("@@", html, name)

    def test_layers_payload_embeds_and_parses(self):
        html = self.pages["full"]
        marker = "var LAYERS = "
        start = html.index(marker) + len(marker)
        end = html.index(";\n", start)
        payload = json.loads(html[start:end].replace("<\\/", "</"))
        self.assertEqual([ld["name"] for ld in payload],
                         [ld["name"] for ld in self.layer_defs])

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
