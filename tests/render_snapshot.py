"""
Render deterministic HTML snapshots of the exporter output without QGIS.

Usage: python3 tests/render_snapshot.py <output_dir>

Imports the real intermap exporter (via the qgis mock package) and calls
WebMapExporter._render_html() with representative synthetic layer payloads.
Used to prove that a refactor leaves the generated web map byte-identical.
"""
import os
import sys
import hashlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "qgis_mock"))
sys.path.insert(0, os.path.dirname(_HERE))


def _vector_layer_def(name, geom_type, features, style_map=None, label=False):
    ld = {
        "kind": "vector",
        "name": name,
        "geomType": geom_type,
        "geojson": {"type": "FeatureCollection", "features": features},
        "styleMap": style_map or {
            "__default__": {
                "kind": geom_type,
                "color": "#1f6feb",
                "weight": 2,
                "opacity": 1.0,
                "fillColor": "#1f6feb",
                "fillOpacity": 0.4,
            }
        },
    }
    if label:
        ld["labelConfig"] = {
            "field": "name",
            "fontFamily": "Arial, sans-serif",
            "fontSize": 11,
            "color": "#222222",
            "bold": False,
            "italic": False,
            "bufferSize": 1.2,
            "bufferColor": "#ffffff",
        }
    return ld


def _feature(fid, geom, props):
    return {"type": "Feature", "id": fid, "geometry": geom, "properties": props}


def build_layer_defs():
    points = _vector_layer_def(
        "Boreholes", "point",
        [
            _feature(1, {"type": "Point", "coordinates": [-0.1, 51.5, 12.0]},
                     {"name": "BH01", "depth": 12.5}),
            _feature(2, {"type": "Point", "coordinates": [-0.11, 51.51]},
                     {"name": "BH02", "depth": 8.0}),
        ],
        style_map={
            "__default__": {
                "kind": "point", "shape": "circle", "radius": 6,
                "color": "#333333", "weight": 1, "opacity": 1.0,
                "fillColor": "#e63329", "fillOpacity": 0.9,
            }
        },
        label=True,
    )
    lines = _vector_layer_def(
        "Routes", "line",
        [_feature(3, {"type": "LineString",
                      "coordinates": [[-0.12, 51.49], [-0.1, 51.5], [-0.09, 51.52]]},
                  {"name": "Route A", "length_m": 3400})],
    )
    polys = _vector_layer_def(
        "Site boundary", "polygon",
        [_feature(4, {"type": "Polygon",
                      "coordinates": [[[-0.13, 51.48], [-0.08, 51.48],
                                       [-0.08, 51.53], [-0.13, 51.53],
                                       [-0.13, 51.48]]]},
                  {"name": "Site", "area_ha": 42.0})],
    )
    wms = {
        "kind": "wms", "name": "Geology WMS", "opacity": 0.8,
        "bounds": [[51.4, -0.2], [51.6, 0.0]],
        "wmsUrl": "https://example.com/wms", "wmsLayers": "geology",
        "wmsFormat": "image/png", "wmsStyles": "", "wmsCrs": "EPSG:3857",
        "wmsVersion": "1.3.0", "tileType": "wms",
        "legendUrl": "https://example.com/wms?REQUEST=GetLegendGraphic",
    }
    raster = {
        "kind": "raster", "name": "Hillshade",
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42m"
                "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
        "bounds": [[51.4, -0.2], [51.6, 0.0]],
        "rasterLegend": {"type": "gradient",
                         "entries": [{"color": "#000000", "label": "0"},
                                     {"color": "#ffffff", "label": "255"}]},
    }
    cog = {
        "kind": "cog", "name": "Ortho COG",
        "url": "https://blob.example.com/ortho.tif",
        "bounds": [[51.4, -0.2], [51.6, 0.0]], "opacity": 1.0, "bands": 3,
    }
    return [points, lines, polys, wms, raster, cog]


LAYER_TREE = [
    {"type": "group", "name": "Investigations", "children": [
        {"type": "layer", "name": "Boreholes"},
        {"type": "layer", "name": "Routes"},
    ]},
    {"type": "layer", "name": "Site boundary"},
    {"type": "group", "name": "Background", "children": [
        {"type": "layer", "name": "Geology WMS"},
        {"type": "layer", "name": "Hillshade"},
        {"type": "layer", "name": "Ortho COG"},
    ]},
]

MAP_VIEWS = [
    {"name": "Overview", "notes": "<b>Whole site</b> overview",
     "extent": [[51.4, -0.2], [51.6, 0.0]],
     "layerIds": ["Boreholes", "Site boundary"]},
    {"name": "North detail", "notes": "",
     "extent": [[51.5, -0.12], [51.53, -0.08]],
     "theme": "north-theme"},
]

INFO_PANEL = {
    "enabled": True,
    "title": "Example Ground Model",
    "text": "Interactive map of the <i>example</i> site investigation.",
    "date": "2026-07-16",
    "client": "Example Client Ltd",
    "project": "Example Project",
    "project_number": "5230001",
    "include_project_info": True,
    "include_doc_metadata": True,
    "originated_name": "AB", "originated_date": "2026-07-01",
    "checked_name": "CD", "checked_date": "2026-07-02",
    "reviewed_name": "EF", "reviewed_date": "2026-07-03",
    "approved_name": "GH", "approved_date": "2026-07-04",
    "doc_number": "DOC-001", "revision": "P02", "purpose": "S2",
}

CHANGELOG = [
    {"rev": "P01", "date": "2026-07-01", "desc": "First issue"},
    {"rev": "P02", "date": "2026-07-16", "desc": "Updated boreholes"},
]

REPORT_MD = """---
title: Example Report
subtitle: Site investigation summary
---

# Introduction

Some *markdown* content linking to [the overview](view:Overview) and
[borehole BH01](gis:Boreholes?name=BH01).

![Figure 1](fig1.png)

# Findings

:::view North detail

More content.
"""

# 1x1 transparent PNG
_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def build_scenarios(tmpdir):
    """Return {scenario_name: WebMapExporter} covering the feature matrix."""
    from intermap.exporter import WebMapExporter

    report_dir = os.path.join(tmpdir, "report")
    figures_dir = os.path.join(report_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    md_path = os.path.join(report_dir, "report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(REPORT_MD)
    with open(os.path.join(figures_dir, "fig1.png"), "wb") as f:
        f.write(_PNG)

    common = dict(layer_tree=LAYER_TREE,
                  initial_extent=[[51.45, -0.15], [51.55, -0.05]])

    scenarios = {
        "minimal": WebMapExporter(
            [], "unused.html",
            include_layer_control=False, include_basemap=True,
            feat_identify=False, feat_attr_table=False, feat_attr_csv=False,
            feat_attr_geojson=False, feat_measure=False, feat_filter=False,
            feat_search=False, feat_minimap=False, feat_fancy_labels=False,
            feat_changelog=False, feat_3d=False, feat_sketch=False,
        ),
        "full": WebMapExporter(
            [], "unused.html",
            map_views=MAP_VIEWS, info_panel=INFO_PANEL, theme="corporate",
            changelog=CHANGELOG,
            cesium_ion_token="TOKEN123", google_maps_key="GKEY456",
            feat_3d_extrude_field="depth", feat_3d_extrude_scale=2.5,
            cog_proxy="https://proxy.example.com/cors?url=",
            **common,
        ),
        "report": WebMapExporter(
            [], "unused.html",
            map_views=MAP_VIEWS, info_panel=INFO_PANEL,
            report_md_path=md_path, report_figures_dir=figures_dir,
            **common,
        ),
        "slate-theme": WebMapExporter(
            [], "unused.html", theme="slate", include_basemap=False,
            **common,
        ),
    }
    return scenarios


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    layer_defs = build_layer_defs()
    bounds = [[51.4, -0.2], [51.6, 0.0]]
    digest_lines = []
    for name, exporter in sorted(build_scenarios(outdir).items()):
        html = exporter._render_html(layer_defs, bounds)
        path = os.path.join(outdir, f"{name}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
        digest_lines.append(f"{sha}  {name}.html ({len(html)} bytes)")
    manifest = os.path.join(outdir, "SHA256SUMS")
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("\n".join(digest_lines) + "\n")
    print("\n".join(digest_lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(_HERE, "..", "_snapshots"))
