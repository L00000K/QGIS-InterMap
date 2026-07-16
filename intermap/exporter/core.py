"""
WebMapExporter: walks the selected layers, builds the export payload and
renders the final self-contained HTML page via template.render_page().
"""
import os
import json

from qgis.core import QgsCoordinateTransform, QgsMapLayer, QgsProject

from .assets import (
    _PLUGIN_DIR, _get_leaflet_assets, _load_plugin_assets, _script_safe_js,
)
from .compat import _WGS84
from .geometry import _flatten_coords, _geom_type_str, _layer_to_geojson
from .labels import _extract_label_config
from .rasters import _build_elevation_dem, _raster_legend_data, _raster_to_base64
from .report import _build_report_payload
from .sources import _parse_cog_source, _parse_wms_source, _wms_legend_url
from .styles import _build_style_map
from .template import render_page
from .themes import _THEMES
from .utils import _richtext_body


class WebMapExporter:
    def __init__(self, layers, output_path,
                 include_layer_control=True, include_basemap=True,
                 progress_callback=None,
                 layer_tree=None, initial_extent=None, map_views=None,
                 info_panel=None, theme=None,
                 feat_identify=True, feat_attr_table=True,
                 feat_attr_csv=True, feat_attr_geojson=True,
                 feat_measure=True, feat_filter=True,
                 feat_search=True, feat_minimap=True, feat_fancy_labels=True,
                 feat_changelog=True, changelog=None,
                 feat_3d=True, feat_sketch=True,
                 cesium_ion_token='', google_maps_key='',
                 feat_3d_extrude_field='', feat_3d_extrude_scale=1.0,
                 feat_3d_elevation_raster=None,
                 report_md_path='', report_figures_dir='',
                 cog_proxy=''):
        self.layers = layers
        self.output_path = output_path
        self.include_layer_control = include_layer_control
        self.include_basemap = include_basemap
        self.progress = progress_callback or (lambda v: None)
        self.layer_tree = layer_tree or []
        self.initial_extent = initial_extent
        self.map_views = map_views or []
        self.info_panel = info_panel or {}
        self.theme = theme or "corporate"
        self.feat_identify = feat_identify
        self.feat_attr_table = feat_attr_table
        self.feat_attr_csv = feat_attr_csv
        self.feat_attr_geojson = feat_attr_geojson
        self.feat_measure = feat_measure
        self.feat_filter = feat_filter
        self.feat_search = feat_search
        self.feat_minimap = feat_minimap
        self.feat_fancy_labels = feat_fancy_labels
        self.feat_changelog = feat_changelog
        self.changelog = changelog or []
        self.feat_3d = feat_3d
        self.feat_sketch = feat_sketch
        self.cesium_ion_token = cesium_ion_token or ''
        self.google_maps_key = google_maps_key or ''
        self.feat_3d_extrude_field = feat_3d_extrude_field or ''
        self.feat_3d_extrude_scale = float(feat_3d_extrude_scale or 1.0)
        self.feat_3d_elevation_raster = feat_3d_elevation_raster or None
        self.report_md_path = (report_md_path or '').strip()
        self.report_figures_dir = (report_figures_dir or '').strip()
        self.cog_proxy = (cog_proxy or '').strip()

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
                    wms_def = {
                        "kind":    "wms",
                        "name":    layer.name(),
                        "opacity": round(layer.opacity(), 3),
                        "bounds": [
                            [wgs.yMinimum(), wgs.xMinimum()],
                            [wgs.yMaximum(), wgs.xMaximum()],
                        ],
                        **wms,
                    }
                    legend_url = _wms_legend_url(wms)
                    if legend_url:
                        wms_def["legendUrl"] = legend_url
                    layer_defs.append(wms_def)
                    continue

                cog = _parse_cog_source(layer)
                if cog:
                    # Remote COG on blob storage — reference by URL, render
                    # client-side. Keeps the export small and avoids embedding
                    # hundreds of MB of raster data.
                    layer_defs.append(cog)
                    continue

                b64, bounds = _raster_to_base64(layer)
                layer_defs.append({
                    "kind":         "raster",
                    "name":         layer.name(),
                    "data":         b64,
                    "bounds":       bounds,
                    "rasterLegend": _raster_legend_data(layer),
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
            if ld["kind"] in ("raster", "wms", "cog"):
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
        _cesium_ion_token    = str(self.cesium_ion_token or '').replace('"', '').replace('\\', '')
        _google_maps_key     = str(self.google_maps_key  or '').replace('"', '').replace('\\', '')
        _extrude_field       = str(self.feat_3d_extrude_field or '').replace('"', '').replace('\\', '')
        _extrude_scale       = self.feat_3d_extrude_scale

        # Elevation raster → embedded WGS-84 heightmap for the 3D terrain
        _elevation_json = "null"
        if self.feat_3d and self.feat_3d_elevation_raster:
            try:
                _elev_layer = QgsProject.instance().mapLayer(self.feat_3d_elevation_raster)
            except Exception:
                _elev_layer = None
            if _elev_layer is not None:
                dem = _build_elevation_dem(_elev_layer)
                if dem:
                    _elevation_json = json.dumps(dem, separators=(",", ":"))
        # Properly escaped JS string literal (safe against injection)
        _cog_proxy_json      = json.dumps(str(self.cog_proxy or ''))

        # Resolve QGIS theme references to layer name lists at export time so the
        # web map JavaScript can toggle layers without needing the QGIS theme API.
        resolved_views = []
        for mv in self.map_views:
            mv_copy = dict(mv)
            if mv_copy.get("theme") and not mv_copy.get("layerIds"):
                try:
                    tc = QgsProject.instance().mapThemeCollection()
                    mv_copy["layerIds"] = [
                        lyr.name() for lyr in tc.mapThemeVisibleLayers(mv_copy["theme"])
                    ]
                except Exception:
                    mv_copy["layerIds"] = []
            if mv_copy.get("notes"):
                mv_copy["notes"] = _richtext_body(mv_copy["notes"])
            resolved_views.append(mv_copy)
        themes_json = json.dumps(resolved_views, separators=(",", ":")).replace("</", "<\\/")

        # ── Report / story mode payload ─────────────────────────────────
        _report_json = "null"
        _report_head = ""
        _report_pane_html = ""
        if self.report_md_path:
            try:
                payload = _build_report_payload(
                    self.report_md_path, self.report_figures_dir,
                    [ld["name"] for ld in layer_defs],
                    [mv.get("name", "") for mv in resolved_views])
                for w in payload["warnings"]:
                    print(f"InterMap report: {w}")
                _report_json = json.dumps(
                    payload, separators=(",", ":")).replace("</", "<\\/")
                _marked_path = os.path.join(_PLUGIN_DIR, "vendor", "marked.min.js")
                if os.path.exists(_marked_path):
                    with open(_marked_path, encoding="utf-8") as f:
                        _report_head = ("<script>\n"
                                        + _script_safe_js(f.read())
                                        + "\n</script>")
                _report_pane_html = (
                    '<div id="report-pane">\n'
                    '  <div id="report-header">\n'
                    '    <div id="report-title"></div>\n'
                    '    <button id="report-collapse" title="Collapse report — full map">&#9668;</button>\n'
                    '  </div>\n'
                    '  <details id="report-toc" open><summary>Contents</summary>'
                    '<div id="report-toc-body"></div></details>\n'
                    '  <div id="report-scroll"><div id="report-content"></div></div>\n'
                    '</div>\n'
                    '<div id="report-divider" title="Drag to resize"></div>'
                )
            except Exception as e:
                print(f"InterMap report skipped: {e}")

        import html as _html_mod
        _info = self.info_panel
        _info_enabled = bool(_info.get("enabled", False))
        _info_title = _html_mod.escape(str(_info.get("title", "") or ""))
        _info_text = _richtext_body(str(_info.get("text", "") or ""))
        _info_date = _html_mod.escape(str(_info.get("date", "") or ""))
        _info_client         = _html_mod.escape(str(_info.get("client", "") or ""))
        _info_project        = _html_mod.escape(str(_info.get("project", "") or ""))
        _info_project_number = _html_mod.escape(str(_info.get("project_number", "") or ""))
        _inc_proj = bool(_info.get("include_project_info", True))
        _inc_dm   = bool(_info.get("include_doc_metadata",  True))
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
        _info_doc_number = _html_mod.escape(str(_info.get("doc_number", "") or ""))
        _info_revision   = _html_mod.escape(str(_info.get("revision",   "") or ""))
        _info_purpose    = _html_mod.escape(str(_info.get("purpose",    "") or ""))
        _client_img_path  = str(_info.get("client_img",  "") or "")
        _project_img_path = str(_info.get("project_img", "") or "")
        _page_title = _html_mod.escape(_info.get("title", "") or "InterMap")

        # ── Theme colours ────────────────────────────────────────────────────
        _t = _THEMES.get(self.theme or "corporate", _THEMES["corporate"])
        _th_hdr     = _t["hdr"]
        _th_hdr_bdr = _t["hdr_bdr"]
        _th_acc     = _t["acc"]
        _th_acc_dk  = _t["acc_dk"]
        _th_acc_lt  = _t["acc_lt"]
        _th_acc_md  = _t["acc_md"]
        _th_acc_ft  = _t["acc_ft"]
        _th_pnl     = _t["pnl"]
        _th_pnl_a   = _t["pnl_a"]
        _th_pnl_r   = _t["pnl_r"]
        _th_txt     = _t["txt"]
        _th_txt2    = _t["txt2"]
        _th_txt3    = _t["txt3"]
        _th_bdr     = _t["bdr"]
        _th_bdr2    = _t["bdr2"]
        _th_map     = _t["map"]
        # 15%-opacity accent for resize handle hovers
        _hex = _th_acc.lstrip("#")
        _th_acc_a15 = f"rgba({int(_hex[0:2],16)},{int(_hex[2:4],16)},{int(_hex[4:6],16)},0.15)"

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
                "<script>\n" + _script_safe_js(js) + "\n</script>"
            )

        plugin_heads = "\n".join(filter(bool, [
            _plugin_block("markercluster"),
            _plugin_block("fullscreen"),
            _plugin_block("minimap"),
            _plugin_block("contextmenu"),
            _plugin_block("geoman") if self.feat_sketch else "",
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
            brand_content = (
                f'<span style="height:22px;display:flex;align-items:center;">'
                f'{_svg_src}</span>'
            )
            _cad_logo_html = f'<div class="cad-logo">{_svg_src}</div>'
        elif os.path.exists(_logo_png):
            import base64 as _b64
            with open(_logo_png, "rb") as _f:
                _logo_b64 = _b64.b64encode(_f.read()).decode("utf-8")
            brand_content = (
                f'<img src="data:image/png;base64,{_logo_b64}"'
                f' alt="AtkinsRéalis" style="height:22px;display:block;">'
            )
            _cad_logo_html = (
                f'<div class="cad-logo"><img src="data:image/png;base64,{_logo_b64}"'
                f' alt="AtkinsRéalis" class="cad-logo-img"></div>'
            )
        else:
            brand_content = (
                '<svg width="26" height="22" viewBox="0 0 26 22" xmlns="http://www.w3.org/2000/svg">'
                '<polygon points="13,1 25,21 1,21" fill="none" stroke="#e63329" stroke-width="2.2"/>'
                '<line x1="7.5" y1="14" x2="18.5" y2="14" stroke="#e63329" stroke-width="2.2"/>'
                '</svg>'
                '<span>AtkinsRéalis</span>'
            )
            _cad_logo_html = f'<div class="cad-logo"><span style="font-weight:700;color:{_th_acc};">AtkinsR&#233;alis</span></div>'
        brand_content_json = json.dumps(brand_content).replace("</", "<\\/")

        # Pre-build left panel HTML (map info + optional map views section)
        _left_panel_needed = _info_enabled or bool(self.map_views)
        if _left_panel_needed:
            _panel_title_html = _info_title if _info_enabled else "Map Views"
            _footer_parts = []
            _cad_block_html = ""
            if _info_enabled:
                if _info_date:
                    _footer_parts.append(f"<span>{_info_date}</span>")

                # ── Helper: embed image file as base64 data URI ────────────────
                def _embed_img(path):
                    if not path or not os.path.isfile(path):
                        return None
                    ext = os.path.splitext(path)[1].lower().lstrip(".")
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                            "png": "image/png", "gif": "image/gif",
                            "webp": "image/webp"}.get(ext, "image/png")
                    try:
                        with open(path, "rb") as _ef:
                            return "data:{};base64,{}".format(
                                mime, _b64.b64encode(_ef.read()).decode())
                    except Exception:
                        return None

                # ── Client section content ─────────────────────────────────────
                _client_b64 = _embed_img(_client_img_path)
                if _client_b64:
                    _client_inner = f'<img class="cad-img" src="{_client_b64}" alt="Client">'
                elif _info_client:
                    _client_inner = f'<div class="cad-value">{_info_client}</div>'
                else:
                    _client_inner = '<div class="cad-img-ph">Client</div>'

                # ── Project section content ────────────────────────────────────
                _project_b64 = _embed_img(_project_img_path)
                if _project_b64:
                    _project_inner = f'<img class="cad-img" src="{_project_b64}" alt="Project">'
                elif _info_project:
                    _project_inner = f'<div class="cad-value">{_info_project}</div>'
                else:
                    _project_inner = '<div class="cad-img-ph">Project</div>'

                # ── Document control rows ──────────────────────────────────────
                _cad_dc_rows = "".join(
                    f'<tr><td class="cad-dc-role">{role}</td>'
                    f'<td class="cad-dc-name">{name}</td>'
                    f'<td class="cad-dc-date">{date}</td></tr>'
                    for role, name, date in _doc_control
                    if name or date
                )

                # ── Assemble CAD title block ───────────────────────────────────
                _rev_poi_html = (
                    '<div class="cad-split">'
                    f'<div class="cad-section"><div class="cad-label">Revision</div>'
                    f'<div class="cad-value">{_info_revision or "&nbsp;"}</div></div>'
                    f'<div class="cad-section"><div class="cad-label">Purpose</div>'
                    f'<div class="cad-value">{_info_purpose or "&nbsp;"}</div></div>'
                    '</div>'
                )

                _dc_section_html = ""
                if _cad_dc_rows:
                    _dc_section_html = (
                        '<div class="cad-section">'
                        '<div class="cad-label">Document Control</div>'
                        f'<table class="cad-dc-table">{_cad_dc_rows}</table>'
                        '</div>'
                    )

                _cad_parts = [
                    '<div class="cad-block">',
                    '<div class="cad-block-hdr" title="Collapse / expand title block">'
                    '<span>Title Block</span>'
                    '<button class="cad-collapse-btn" aria-label="Collapse title block">&#9650;</button>'
                    '</div>',
                    '<div class="cad-block-body">',
                    f'<div class="cad-section"><div class="cad-label">Produced By</div>'
                    f'{_cad_logo_html}</div>',
                ]
                if _inc_proj:
                    _cad_parts.append(
                        f'<div class="cad-section"><div class="cad-label">Client</div>'
                        f'{_client_inner}</div>'
                    )
                    if _info_project_number:
                        _cad_parts.append(
                            f'<div class="cad-section"><div class="cad-label">Project Number</div>'
                            f'<div class="cad-value">{_info_project_number}</div></div>'
                        )
                    _cad_parts.append(
                        f'<div class="cad-section"><div class="cad-label">Project</div>'
                        f'{_project_inner}</div>'
                    )
                _cad_parts.append(
                    f'<div class="cad-section"><div class="cad-label">Document Name</div>'
                    f'<div class="cad-value">{_info_title or "&nbsp;"}</div></div>'
                )
                if _inc_dm and _info_doc_number:
                    _cad_parts.append(
                        f'<div class="cad-section"><div class="cad-label">Document Number</div>'
                        f'<div class="cad-value">{_info_doc_number}</div></div>'
                    )
                if _inc_dm:
                    _cad_parts.append(_rev_poi_html)
                _cad_parts.append(_dc_section_html)
                _cad_parts.append('</div>')  # close cad-block-body
                _cad_parts.append('</div>')  # close cad-block
                _cad_block_html = "".join(_cad_parts)

            _footer_html = (
                f'<div id="left-panel-footer">{"".join(_footer_parts)}</div>'
                if _footer_parts else ""
            )

            if self.feat_changelog and self.changelog:
                _cl_items = ''.join(
                    f'<li><span class="cl-rev">{e.get("rev","—")}</span>'
                    f'<span class="cl-date">{e.get("date","")}</span>'
                    f'<span class="cl-text">{e.get("text","")}</span></li>'
                    for e in reversed(self.changelog)
                )
                _changelog_html = (
                    '<div id="changelog-section">'
                    '<div id="changelog-hdr" title="Collapse / expand changelog">'
                    '<span>Changelog</span>'
                    '<button class="cad-collapse-btn" aria-label="Collapse changelog">&#9650;</button>'
                    '</div>'
                    f'<ul id="changelog-list">{_cl_items}</ul>'
                    '</div>'
                )
            else:
                _changelog_html = ''

            if _info_enabled:
                _body_html = (
                    f'<div id="left-panel-body">'
                    f'<div class="left-panel-body-top">'
                    f'<div class="left-panel-desc">{_info_text or "&nbsp;"}</div>'
                    f'<div id="map-views-section"></div>'
                    f'{_changelog_html}'
                    f'</div>'
                    f'{_cad_block_html}'
                    f'</div>'
                    f'{_footer_html}'
                )
            else:
                _body_html = (
                    f'<div id="left-panel-body">'
                    f'<div class="left-panel-body-top">'
                    f'<div id="map-views-section"></div>'
                    f'{_changelog_html}'
                    f'</div>'
                    f'</div>'
                )
            left_panel_html = (
                f'<div id="left-panel">'
                f'<div id="left-panel-hdr">'
                f'<span id="left-panel-title">{_panel_title_html}</span>'
                f'<button id="left-panel-close" title="Close">&#10005;</button>'
                f'</div>'
                f'{_body_html}'
                f'<div id="left-panel-resize-h"></div>'
                f'</div>'
            )
        else:
            left_panel_html = ""

        # ── Feature flags ─────────────────────────────────────────────────────
        _feat_js = json.dumps({
            "identify":    self.feat_identify,
            "attrTable":   self.feat_attr_table,
            "attrCsv":     self.feat_attr_csv,
            "attrGeojson": self.feat_attr_geojson,
            "measure":     self.feat_measure,
            "filter":      self.feat_filter,
            "search":      self.feat_search,
            "minimap":     self.feat_minimap,
            "fancyLabels": self.feat_fancy_labels,
            "changelog":   self.feat_changelog,
            "cesium3d":    self.feat_3d,
            "sketch":      self.feat_sketch,
        })

        # Pre-build optional HTML panels
        _select_btn_html = (
            '<button id="attr-select-btn" title="Drag to select features"'
            ' style="background:none;border:none;cursor:pointer;padding:2px 4px;'
            'color:rgba(255,255,255,0.75);display:flex;align-items:center;">'
            '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="9" y="1" width="9" height="6.5" rx="0.6" fill="none"'
            ' stroke="currentColor" stroke-width="1.3"/>'
            '<line x1="9" y1="3.8" x2="18" y2="3.8" stroke="currentColor" stroke-width="1"/>'
            '<line x1="13.5" y1="3.8" x2="13.5" y2="7.5" stroke="currentColor" stroke-width="1"/>'
            '<path d="M2 9L2 19L5.5 15.5L8.5 20.5L10.5 19.5L7.5 14.5L12 14.5Z" fill="currentColor"/>'
            '</svg></button>'
        ) if self.feat_attr_table else ''

        _attr_csv_btn_html = (
            '<button id="attr-table-csv" title="Export CSV">'
            '&#8595;&nbsp;CSV</button>'
        ) if self.feat_attr_csv else ''

        _attr_geojson_btn_html = (
            '<button id="attr-table-geojson" title="Export GeoJSON">'
            '&#8595;&nbsp;GeoJSON</button>'
        ) if self.feat_attr_geojson else ''

        _attr_table_panel_html = (
            '<div id="attr-table-panel">\n'
            '  <div id="attr-table-hdr">\n'
            '    <span>Attribute Table</span>\n'
            '    <select id="attr-table-layer"></select>\n'
            '    <span id="attr-select-badge"></span>\n'
            '    <button id="attr-select-clear" title="Clear selection">&#10005; Clear</button>\n'
            f'    {_select_btn_html}\n'
            '    <input id="attr-table-search" type="text" placeholder="Search…" autocomplete="off">\n'
            f'    {_attr_csv_btn_html}\n'
            f'    {_attr_geojson_btn_html}\n'
            '    <button id="attr-table-close" title="Close">&#10005;</button>\n'
            '  </div>\n'
            '  <div id="attr-table-body"></div>\n'
            '</div>'
        ) if self.feat_attr_table else ''

        _filterbar_html = (
            '<div id="filterbar" style="display:none">\n'
            '  <label>Filter</label>\n'
            '  <select id="filter-layer" title="Layer"></select>\n'
            '  <select id="filter-attr" title="Attribute"></select>\n'
            '  <span id="filter-values-wrap">\n'
            '    <button id="filter-values-btn" type="button">All values</button>\n'
            '    <div id="filter-values-panel">\n'
            '      <input id="filter-values-search" type="text"'
            ' placeholder="Type to search / filter…" autocomplete="off">\n'
            '      <div id="filter-values-list"></div>\n'
            '    </div>\n'
            '  </span>\n'
            '  <button id="filter-clear" type="button">Clear</button>\n'
            '  <span id="filter-count" class="filter-count"></span>\n'
            '</div>'
        ) if self.feat_filter else ''

        _searchbar_html = (
            '<div id="searchbar" style="display:none">\n'
            '  <label>Search</label>\n'
            '  <input id="search-input" type="text"'
            ' placeholder="Highlight features containing… (press Enter)" autocomplete="off">\n'
            '  <button id="search-clear" type="button">Clear</button>\n'
            '  <span id="search-count" class="filter-count"></span>\n'
            '</div>'
        ) if self.feat_search else ''
        return render_page({
            "layers_json": layers_json,
            "bounds_json": bounds_json,
            "initial_bounds_json": initial_bounds_json,
            "include_legend": include_legend,
            "include_basemap_json": include_basemap_json,
            "tree_json": tree_json,
            "themes_json": themes_json,
            "brand_content_json": brand_content_json,
            "leaflet_head": leaflet_head,
            "plugin_heads": plugin_heads,
            "left_panel_html": left_panel_html,
            "_page_title": _page_title,
            "_report_head": _report_head,
            "_report_json": _report_json,
            "_report_pane_html": _report_pane_html,
            "_feat_js": _feat_js,
            "_filterbar_html": _filterbar_html,
            "_searchbar_html": _searchbar_html,
            "_attr_table_panel_html": _attr_table_panel_html,
            "_cesium_ion_token": _cesium_ion_token,
            "_google_maps_key": _google_maps_key,
            "_extrude_field": _extrude_field,
            "_extrude_scale": _extrude_scale,
            "_elevation_json": _elevation_json,
            "_cog_proxy_json": _cog_proxy_json,
            "_th_hdr": _th_hdr,
            "_th_hdr_bdr": _th_hdr_bdr,
            "_th_acc": _th_acc,
            "_th_acc_dk": _th_acc_dk,
            "_th_acc_lt": _th_acc_lt,
            "_th_acc_md": _th_acc_md,
            "_th_pnl_r": _th_pnl_r,
            "_th_acc_a15": _th_acc_a15,
        })
