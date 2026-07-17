# Architecture — QGIS Web Map Exporter

## 1. File map

```
intermap/
├── __init__.py              classFactory() → WebMapExporterPlugin
├── plugin.py                Plugin class: menu item, toolbar button, dialog trigger
├── dialog/                  Export dialog package (PyQt5 dock widget)
│   ├── __init__.py          re-exports WebMapExportDialog
│   ├── main.py              dialog shell: init, settings, header, tab switching
│   ├── constants.py         _SETTINGS_KEY, purposes, brand colours
│   ├── widgets.py           _VResizeHandle, _RectExtentTool
│   ├── richtext.py          RichTextMixin — editor toolbars
│   ├── configs.py           ConfigsMixin — named configs, persistence, import/export
│   ├── info_tab.py          MapInfoTabMixin — title block, doc control, changelog
│   ├── views_tab.py         MapViewsTabMixin — views, extents, theme/layout links
│   ├── layers_tab.py        LayersTabMixin — layer tree, required layers
│   ├── lite.py              LiteModeMixin — simplified export flow
│   └── export_tab.py        ExportTabMixin — export tab + export run
├── exporter/                Export engine package
│   ├── __init__.py          re-exports WebMapExporter
│   ├── core.py              WebMapExporter: export() + template context building
│   ├── compat.py            version-tolerant QGIS imports (_WGS84, optional classes)
│   ├── utils.py             rich-text body, colours, unit conversion
│   ├── assets.py            Leaflet / plugin / vendor asset loading + script-safe JS
│   ├── themes.py            _THEMES colour tokens
│   ├── sources.py           WMS/WMTS/XYZ + remote COG source parsing
│   ├── markers.py           shape aliases, QGIS symbol → inline SVG
│   ├── labels.py            _extract_label_config
│   ├── styles.py            renderers/symbol layers → styleMap dicts
│   ├── geometry.py          layer → GeoJSON, _flatten_coords
│   ├── rasters.py           raster PNG embedding, legends, elevation DEM
│   ├── report.py            report front matter, figures, reference checks
│   ├── template.py          page assembly + @@placeholder@@ substitution
│   └── templates/           the exported web app as plain HTML/CSS/JS
│       ├── head.html        <head> with asset placeholders
│       ├── webmap.css       all page styles
│       ├── body.html        page markup
│       ├── app.js           2D map application (main IIFE)
│       ├── cesium.js        3D viewer IIFE
│       └── report.js        report / story-mode IIFE
├── metadata.txt             QGIS plugin manifest
└── vendor/                  bundled Leaflet 1.9.4 + plugins, marked, PDF.js, logo

tests/                       (repo only — not shipped in the plugin zip)
├── qgis_mock/               importable stand-in for the qgis package
├── test_exporter.py         unit tests against the real modules
├── render_snapshot.py       renders full export scenarios (regression oracle)
└── browser_check.py         boots exports in headless Chromium, fails on JS errors
```

---

## 2. Data flow

```
User clicks "Export"
        │
        ▼
WebMapExportDialog._export()
  ├─ walks QgsProject.instance().layerTreeRoot()
  │    to build panel_layers[] (export order) and tree_nodes[] (LAYER_TREE)
  ├─ reads self._themes[] (from Themes tab)
  └─ calls WebMapExporter(layers, output_path, layer_tree, initial_extent, scenes=themes)

WebMapExporter.export()
  ├─ for each layer:
  │    ├─ _extract_symbol_style(renderer, sym_opacity)
  │    │    └─ returns styleMap dict {category_key: style_dict}
  │    ├─ _extract_label_config(layer)
  │    │    └─ returns labelConfig dict or None
  │    ├─ layer.getFeatures() → GeoJSON dicts
  │    └─ appends LayerDef dict to layer_defs[]
  └─ _render_html(layer_defs, bounds)
       ├─ builds the template context (JSON payloads, feature flags,
       │    theme colours, panel HTML fragments)
       └─ template.render_page(ctx) → writes single HTML file to output_path
```

---

## 3. Python key functions

### `dialog.py — WebMapExportDialog`

| Method | Purpose |
|---|---|
| `__init__` | Captures initial canvas extent via `_capture_canvas_extent()` before UI renders |
| `_capture_canvas_extent()` | Reads `iface.mapCanvas().extent()`, re-projects to WGS-84, returns `[[s,w],[n,e]]` |
| `_build_ui()` | Constructs the two-tab dialog (Layers + Themes) |
| `_populate_layers()` | Recursively walks the QGIS layer tree; groups → non-checkable headers, layers → checkboxes |
| `_export()` | Builds `panel_layers[]` + `tree_nodes[]` by re-walking the tree; calls `WebMapExporter` |
| `_theme_save()` | Snapshots current Layers tab state + form fields into `self._themes[]` |
| `_theme_capture_extent()` | Calls `_capture_canvas_extent()` and stores on the form being edited |

### `exporter/ — symbol extraction`

| Function | Input | Output |
|---|---|---|
| `_extract_symbol_style(renderer, opacity)` | `QgsFeatureRenderer`, float | `{"__default__": style_dict, ...}` |
| `_extract_single_style(symbol, opacity)` | `QgsSymbol` | `style_dict` |
| `_extract_label_config(layer)` | `QgsVectorLayer` | `labelConfig dict` or `None` |
| `_encode_marker_shape(sl)` | `QgsSimpleMarkerSymbolLayer` | shape name string |
| `_color_to_hex(color)` | `QColor` | `"#rrggbb"` |
| `_size_to_px(size, unit)` | float, `QgsUnitTypes.RenderUnit` | float pixels |

### `exporter/core.py — WebMapExporter`

| Method | Purpose |
|---|---|
| `export()` | Iterates layers, builds `layer_defs[]`, calls `_render_html()` |
| `_render_html(layer_defs, bounds)` | Serialises all data to JSON, builds the template context, calls `template.render_page()` |

### `exporter/template.py — page assembly`

The exported page lives in `exporter/templates/` as ordinary HTML/CSS/JS
files containing `@@name@@` placeholders. `render_page(ctx)` concatenates the
parts (head → style → body → app.js → cesium.js → report.js) and substitutes
every placeholder in a single regex pass, so placeholder-like text inside
substituted values (e.g. user data in the GeoJSON payload) is never
re-processed. A missing context key raises immediately rather than emitting a
broken page.

---

## 4. LayerDef dict schema

```python
{
  # Common
  "name": str,               # layer.name()
  "type": "vector" | "raster" | "wms" | "xyz",
  "opacity": float,          # 0.0–1.0, from layer.opacity()
  "visible": bool,

  # Vector only
  "geomType": "Point" | "LineString" | "Polygon",
  "geojson": {               # FeatureCollection
    "type": "FeatureCollection",
    "features": [
      {"type": "Feature", "geometry": {...}, "properties": {...}}
    ]
  },
  "styleMap": {              # keyed by category value or "__default__"
    "__default__": style_dict
  },
  "styleField": str | None,  # field name used for categorisation
  "labelConfig": {           # None if no labels
    "field": str,
    "isExpr": bool,
    "enabled": bool,
    "fontSize": int,
    "fontColor": str,
    "fontOpacity": float,
    "fontFamily": str,
    "bold": bool,
    "italic": bool,
    "bufferSize": int,       # optional
    "bufferColor": str,      # optional
  },

  # Raster only
  "imageData": str,          # base64 data URI
  "bounds": [[s,w],[n,e]],

  # WMS/XYZ only
  "wmsUrl": str,
  "wmsLayers": str,          # WMS only
  "wmsFormat": str,          # WMS only
}
```

---

## 5. Style dict schema

```python
# Point marker
{
  "markerColor": "#rrggbb",
  "markerOpacity": float,
  "markerStrokeColor": "#rrggbb",
  "markerStrokeOpacity": float,
  "markerStrokeWidth": float,     # 0 = NoPen
  "markerSize": int,              # pixels, min 4
  "markerShape": str,             # "circle" | "square" | ...
  "markerAngle": float,           # degrees
}

# Line
{
  "color": "#rrggbb",
  "opacity": float,
  "weight": float,
  "dashArray": str,               # optional, e.g. "8 4"
}

# Polygon fill
{
  "fillColor": "#rrggbb",
  "fillOpacity": float,
  "color": "#rrggbb",             # stroke
  "opacity": float,
  "weight": float,
}
```

---

## 6. JavaScript architecture (embedded in the HTML)

The exported HTML contains a single `<script>` block that runs as an IIFE. All data is injected as JSON literals before the IIFE runs.

### Global JS variables (injected)

```javascript
var LAYERS = [...];          // LayerDef array (see §4 above)
var INCLUDE_LEGEND = true;
var LAYER_TREE = [...];      // nested {type, name, children[], index} nodes
var THEMES = [...];          // theme objects (empty = no dropdown shown)
// map is initialised to:
map.fitBounds(initial_bounds_json);
```

### Key JS data structures

```javascript
// displayItems[] — one entry per exported layer, in render order
{
  ld: LayerDef,              // raw layer definition
  leafletLayer: L.Layer,     // the actual Leaflet layer object
  visible: bool,
  opacity: float,
  paneName: "layerPane0",    // dedicated Leaflet pane (z-index 400+i)
  labelPaneName: "labelPane0", // label pane (z-index 650+i, pointerEvents:none)
  labelsVisible: bool,
  labelLayoutFn: Function,   // runs collision detection, called on moveend/zoomend
  checkbox: HTMLElement,     // legend checkbox
  layerDiv: HTMLElement,     // legend row element
  _infoHtml: str,            // set per-feature during onEachFeature (vectors)
}
```

### Key JS functions

| Function | Purpose |
|---|---|
| `makeMarker(latlng, style, pane)` | Returns `L.circleMarker` (circle) or `L.marker` with `L.divIcon` SVG (other shapes) |
| `shapeSvgInner(shape, cx, cy, r, fill, fillOp, stroke, strokeW, strokeOp)` | Generates the inner SVG path/polygon element for non-circle shapes |
| `buildLayer(item)` | Creates the Leaflet layer for one `displayItem`; attaches `onEachFeature` storing `_infoHtml` per feature |
| `buildLabels(item)` | Binds permanent Leaflet tooltips; attaches `layoutLabels` collision detection on `moveend`/`zoomend` |
| `buildLayerRow(item, container)` | Renders one legend row with checkbox, swatch, cog button |
| `buildLegendNodes(nodes, container)` | Recursively renders LAYER_TREE into the legend panel |
| `setLayerVisible(item, bool)` | Adds/removes from map, toggles label pane |
| `setLayerLabels(item, bool)` | Shows/hides label pane, re-runs collision detection |
| `setLayerOpacity(item, float)` | Updates Leaflet layer opacity and label pane opacity |
| `applyTheme(idx)` | Applies THEMES[idx]: sets layer visibility, fitBounds to saved extent |
| `populateAttrTable()` | Fills the attribute table panel for the currently selected layer |

### Layer pane strategy

Each exported layer gets two dedicated Leaflet panes so draw order and pointer-event behaviour can be controlled independently:

```
layerPane{i}   z-index: 400 + i   (features)
labelPane{i}   z-index: 650 + i   pointerEvents: none   (labels)
```

Label panes use `pointerEvents: none` so labels don't intercept map clicks.

---

## 7. Collision detection algorithm

Runs after each `moveend`/`zoomend` and once on a 150 ms timeout after labels are first built.

```
for each .leaflet-tooltip element in the label pane:
  if its getBoundingClientRect has zero size → skip (not rendered)
  check against all already-placed rects with 3 px padding
  if clash → set visibility: hidden
  else → add to placed list, keep visible
```

Greedy first-wins. Ordering is DOM order (which reflects GeoJSON feature order). Restores all to visible before each pass so the result is zoom-level-aware.

---

## 8. Multi-feature click handler

A single `map.on('click', handler)` collects overlapping features:

```javascript
map.on('click', function(e) {
  var clickPt = map.latLngToContainerPoint(e.latlng);
  var found = [];

  // walk all displayItems
  displayItems.forEach(function(item) {
    if (!item.visible || item.ld.type !== 'vector') return;
    item.leafletLayer.eachLayer(function(fl) {
      // convert feature centroid/path to container point
      // if distance ≤ 10px → push {name, html}
    });
  });

  if (found.length === 0) return;
  if (found.length === 1) { showInfo(found[0].html); return; }

  // Show numbered pick-list; each item click drills into that feature
  // with a ‹ Back button that re-renders the pick-list
});
```

---

## 9. Testing strategy

Three layers, none requiring a QGIS installation:

1. **Unit tests** — `tests/test_exporter.py` imports the real plugin modules
   through `tests/qgis_mock/` (a minimal stand-in for the `qgis` package) and
   covers colours, units, rich text, coordinate flattening, SVG id
   namespacing, dash/hatch styles, DEM grid sizing and quantisation, report
   front matter and reference validation, script-safe JS escaping, template
   placeholder integrity, and end-to-end page rendering invariants.

2. **Snapshot rendering** — `tests/render_snapshot.py` renders four full
   export configurations (minimal, full-featured, report mode, theme
   fallback) through the real `WebMapExporter._render_html()` and writes
   SHA-256 hashes, so refactors can be proven output-identical.

3. **Browser checks** — `tests/browser_check.py` opens each rendered export
   in headless Chromium and fails on any JavaScript error (network noise from
   offline tile servers is filtered out).

Run with: `python3 -m unittest discover tests -v`
