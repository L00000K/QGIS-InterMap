"""Build a demo export for the layout figure.

Renders a small, presentable project through the real exporter (via the qgis
mock) so the figure is a screenshot of genuine output rather than a mock-up.

Writes build/fig_demo.html next to this script; make_figure.py screenshots it.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "tests", "qgis_mock"))
sys.path.insert(0, _REPO)

from intermap.exporter import WebMapExporter  # noqa: E402

OUT = os.path.join(_HERE, "fig_demo.html")


def qt_html(inner):
    """Wrap a fragment the way QTextEdit.toHtml() would.

    _richtext_body() only unwraps a full Qt document; a bare fragment is
    escaped and would render as literal markup in the figure.
    """
    return ("<!DOCTYPE HTML><html><head><meta charset='utf-8'></head>"
            "<body style=\" font-family:'Segoe UI'; font-size:9pt;\">"
            f"{inner}</body></html>")


def feat(fid, geom, props):
    return {"type": "Feature", "id": fid, "geometry": geom, "properties": props}


# Point symbols read marker* keys (see makeMarker in app.js); lines and
# polygons read color / fillColor (leafletPathStyle).
PT_STYLE = {"type": "single", "style": {
    "kind": "point",
    "markerShape": "circle", "markerSize": 14,
    "markerColor": "#E63329", "markerOpacity": 0.95,
    "markerStrokeColor": "#3A3A3A", "markerStrokeWidth": 1.5,
    "markerStrokeOpacity": 1.0}}

boreholes = {
    "kind": "vector", "name": "Boreholes", "geomType": "point",
    "geojson": {"type": "FeatureCollection", "features": [
        feat(1, {"type": "Point", "coordinates": [-0.1042, 51.5121]},
             {"name": "BH01", "depth_m": 12.5, "method": "Cable percussion"}),
        feat(2, {"type": "Point", "coordinates": [-0.0994, 51.5154]},
             {"name": "BH02", "depth_m": 8.0, "method": "Rotary"}),
        feat(3, {"type": "Point", "coordinates": [-0.1088, 51.5178]},
             {"name": "BH03", "depth_m": 15.2, "method": "Cable percussion"}),
        feat(4, {"type": "Point", "coordinates": [-0.0951, 51.5098]},
             {"name": "BH04", "depth_m": 6.4, "method": "Window sample"}),
    ]},
    "styleMap": PT_STYLE,
    "labelConfig": {"enabled": True, "field": "name", "fontSize": 11,
                    "fontColor": "#111111", "bufferSize": 1.4,
                    "bufferColor": "#ffffff", "bold": True},
}

route = {
    "kind": "vector", "name": "Access route", "geomType": "line",
    "geojson": {"type": "FeatureCollection", "features": [
        feat(5, {"type": "LineString", "coordinates": [
            [-0.1120, 51.5075], [-0.1042, 51.5121], [-0.0975, 51.5169]]},
             {"name": "Site access", "length_m": 1420})]},
    "styleMap": {"type": "single", "style": {
        "kind": "line", "color": "#F5A623", "weight": 4, "opacity": 1.0}},
    "labelConfig": None,
}

boundary = {
    "kind": "vector", "name": "Site boundary", "geomType": "polygon",
    "geojson": {"type": "FeatureCollection", "features": [
        feat(6, {"type": "Polygon", "coordinates": [[
            [-0.1140, 51.5060], [-0.0930, 51.5060],
            [-0.0930, 51.5200], [-0.1140, 51.5200], [-0.1140, 51.5060]]]},
             {"name": "Application boundary", "area_ha": 21.4})]},
    "styleMap": {"type": "single", "style": {
        "kind": "polygon", "color": "#2D7DD2", "weight": 2, "opacity": 1.0,
        "fillColor": "#2D7DD2", "fillOpacity": 0.12}},
    "labelConfig": None,
}

LAYERS = [boreholes, route, boundary]

# Index-based tree — the form intermap/dialog/export_tab.py really emits. A
# name-based tree silently drops every grouped layer from the legend.
TREE = [
    {"type": "group", "name": "Investigation", "children": [
        {"type": "layer", "index": 0},
        {"type": "layer", "index": 1},
    ]},
    {"type": "layer", "index": 2},
]

MAP_VIEWS = [
    {"name": "Site overview",
     "notes": qt_html("<p><b>Whole site</b> — all investigation points</p>"),
     "extent": [[51.5040, -0.1170], [51.5215, -0.0910]],
     "layerIds": ["Boreholes", "Access route", "Site boundary"]},
    {"name": "Northern extent",
     "notes": qt_html("<p>Detail around <b>BH03</b></p>"),
     "extent": [[51.5150, -0.1120], [51.5200, -0.0960]],
     "layerIds": ["Boreholes", "Site boundary"]},
]

INFO_PANEL = {
    "enabled": True,
    "title": "Example Ground Model",
    "text": qt_html("<p>Interactive ground model for the <i>Example</i> site "
                    "investigation. Click any borehole for its log summary.</p>"),
    "client": "Example Client Ltd",
    "project": "Example Project",
    "project_number": "5230001",
    "doc_number": "5230001-XX-GM-001",
    "revision": "P02",
    "purpose": "S2 — Suitable for information",
    "created_by_name": "A. Bloggs",
    "originated_name": "AB", "originated_date": "2026-07-01",
    "checked_name": "CD", "checked_date": "2026-07-02",
    "reviewed_name": "EF", "reviewed_date": "2026-07-03",
    "approved_name": "GH", "approved_date": "2026-07-04",
    "show_project_info": True, "show_doc_metadata": True, "show_doc_control": True,
}

CHANGELOG = [
    {"rev": "P01", "date": "2026-07-01", "text": "First issue"},
    {"rev": "P02", "date": "2026-07-16", "text": "BH03 and BH04 added"},
]

EXTENT = [[51.5040, -0.1170], [51.5215, -0.0910]]


def main():
    exporter = WebMapExporter(
        [], "unused.html",
        layer_tree=TREE, initial_extent=EXTENT,
        map_views=MAP_VIEWS, info_panel=INFO_PANEL, theme="corporate",
        changelog=CHANGELOG, include_basemap=True, basemap_greyscale=True,
    )
    html = exporter._render_html(LAYERS, EXTENT)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote", OUT, len(html), "bytes")


if __name__ == "__main__":
    main()
