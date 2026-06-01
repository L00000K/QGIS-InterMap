# Architecture — QGIS Web Map Exporter

## 1. File map

```
qgis_webmap/
├── __init__.py              classFactory() → QgisWebMapPlugin
├── plugin.py                Plugin class: menu item, toolbar button, dialog trigger
├── dialog.py                WebMapExportDialog (PyQt5)
├── exporter.py              WebMapExporter + _render_html() HTML template
├── test_exporter_logic.py   18 unit tests (no QGIS required)
├── metadata.txt             QGIS plugin manifest
└── vendor/
    ├── leaflet.js           Leaflet 1.9.4 (bundled)
    ├── leaflet.css
    ├── leaflet.fullscreen.js / .css
    ├── leaflet.minimap.js / .css
    ├── leaflet.contextmenu.js / .css
    └── logo.svg / logo.png  (optional branding)
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
       └─ writes single HTML file to output_path
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

### `exporter.py — symbol extraction`

| Function | Input | Output |
|---|---|---|
| `_extract_symbol_style(renderer, opacity)` | `QgsFeatureRenderer`, float | `{"__default__": style_dict, ...}` |
| `_extract_single_style(symbol, opacity)` | `QgsSymbol` | `style_dict` |
| `_extract_label_config(layer)` | `QgsVectorLayer` | `labelConfig dict` or `None` |
| `_encode_marker_shape(sl)` | `QgsSimpleMarkerSymbolLayer` | shape name string |
| `_color_to_hex(color)` | `QColor` | `"#rrggbb"` |
| `_size_to_px(size, unit)` | float, `QgsUnitTypes.RenderUnit` | float pixels |

### `exporter.py — WebMapExporter`

| Method | Purpose |
|---|---|
| `export()` | Iterates layers, builds `layer_defs[]`, calls `_render_html()` |
| `_render_html(layer_defs, bounds)` | Serialises all data to JSON, injects into the f-string HTML template |

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

Tests in `test_exporter_logic.py` mock the QGIS module tree so they run with plain Python. They cover:

- Colour conversion (`_color_to_hex`)
- Coordinate flattening (`_flatten_coords`) for all geometry types
- GeoJSON structure output
- Style dict serialisability for all renderer types
- HTML output contains expected Leaflet markers
- Unit conversion (`_size_to_px`) for px, mm, pt
- Marker shape alias resolution
- WMS layer def serialisability

Run with: `python3 -m pytest qgis_webmap/test_exporter_logic.py -v`
