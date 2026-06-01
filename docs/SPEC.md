# Plugin Specification — QGIS Web Map Exporter

## 1. Purpose

The QGIS Web Map Exporter plugin produces a **single, self-contained HTML file** that faithfully reproduces the appearance and interactivity of a QGIS project in any modern web browser. No web server, no Node.js, no GIS expertise required by the end user — just a `.html` file.

The target audience is a GIS analyst who wants to share a styled map with non-GIS colleagues or clients who need to explore it, filter it, and click features.

---

## 2. Plugin dialog

The dialog opens when the user invokes **Web → Web Map Exporter → Export to Web Map…**. It captures the current QGIS canvas extent at open time, before any user interaction can change it.

### 2.1 Layers tab

- Lists all vector and raster layers from the QGIS layer tree.
- Layer **groups** appear as non-checkable grey headers (e.g. `▸ Group Name`); child layers are indented beneath them.
- Each layer has a checkbox. Layers already selected in the QGIS Layers panel are pre-checked; otherwise visible layers are pre-checked.
- **Select All / Deselect All** buttons.
- **Include legend / layer control** checkbox (default: on).
- **Output file** path field + Browse button (defaults to the QGIS project directory).

### 2.2 Themes tab

Themes are optional named presets that a map viewer can switch between using a dropdown in the exported HTML.

Each theme stores:
- **Name** (required) — shown in the dropdown.
- **Notes** — short description shown as a subtitle in the dropdown option.
- **Layer visibility** — which layers are visible when the theme is applied (snapshot of the current Layers tab checkboxes at save time).
- **Extent** — optional map extent captured from the current QGIS canvas view via the "📷 Capture current QGIS view" button.

Themes can be reordered (Up/Down), edited (select → modify form → Save), and deleted. If no themes are defined, the exported HTML contains no themes dropdown.

---

## 3. Export process

```
QGIS Layers
    ↓
_extract_symbol_style()   — per-symbol-layer type, per renderer type
_extract_label_config()   — QgsPalLayerSettings → font, buffer, field
layer.getFeatures()        — geometries → GeoJSON dicts
    ↓
layer_defs[]              — list of layer definition dicts
    ↓
_render_html()            — Python f-string template → single HTML file
```

Each layer becomes a dict (`LayerDef`) with the following keys (subset shown):

```json
{
  "name": "My Layer",
  "type": "vector",
  "geomType": "Point",
  "geojson": { "type": "FeatureCollection", "features": [...] },
  "styleMap": { "__default__": { "markerColor": "#ff0000", ... } },
  "labelConfig": { "field": "NAME", "fontSize": 12, ... },
  "opacity": 1.0,
  "visible": true
}
```

---

## 4. Supported layer types

| Layer type | Export method |
|---|---|
| Vector — point | GeoJSON + Leaflet `circleMarker` or `divIcon` SVG marker |
| Vector — line | GeoJSON + Leaflet `polyline` with dash pattern |
| Vector — polygon | GeoJSON + Leaflet `polygon` |
| Raster | Base64-encoded PNG image overlay (`L.imageOverlay`) |
| WMS | Live `L.tileLayer.wms` (streams from server at view time) |
| XYZ/WMTS tile layer | Live `L.tileLayer` |

---

## 5. Symbology support

### 5.1 Renderer types

| Renderer | Behaviour |
|---|---|
| Single symbol | One style applied to all features |
| Categorised | Per-value style map keyed by the category field value |
| Graduated | Per-range style map, each range keyed by a sentinel string |
| Rule-based | First matching rule wins; falls back to `__default__` |

### 5.2 Symbol layer types

**Point markers** (`QgsSimpleMarkerSymbolLayer`)

| Property | JS key | Notes |
|---|---|---|
| Fill colour + alpha | `markerColor`, `markerOpacity` | Combined with renderer opacity |
| Stroke colour + alpha | `markerStrokeColor`, `markerStrokeOpacity` | Min 0.5 px when not NoPen |
| Stroke width | `markerStrokeWidth` | 0 when NoPen |
| Size | `markerSize` | Minimum 4 px |
| Shape | `markerShape` | See §5.3 |
| Rotation | `markerAngle` | Degrees |

**SVG markers** (`QgsSvgMarkerSymbolLayer`) — fall back to circle with fill/stroke colours extracted.

**Lines** (`QgsSimpleLineSymbolLayer`)

| Property | JS key |
|---|---|
| Colour + alpha | `color`, `opacity` |
| Width | `weight` |
| Pen style | `dashArray` (solid/dash/dot/dash-dot/dash-dot-dot/custom) |

**Fills** (`QgsSimpleFillSymbolLayer`)

| Property | JS key |
|---|---|
| Fill colour + alpha | `fillColor`, `fillOpacity` |
| Stroke colour + alpha | `color`, `opacity` |
| Stroke width | `weight` |

### 5.3 Marker shapes

`circle`, `square`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`, `star`, `cross`, `x`

Circles use `L.circleMarker` (canvas-rendered). All other shapes use `L.divIcon` with an inline SVG, supporting fill, stroke, opacity and rotation.

---

## 6. Labels

Extracted from `QgsPalLayerSettings` (requires QGIS >= 3.x labelling API).

| Property | Notes |
|---|---|
| Field / expression | `isExpr: true` for expression-based labels |
| Enabled state | Mirrors the layer's `labelsEnabled()` at export time |
| Font family | Appended with `, Arial, sans-serif` for web fallback |
| Font size | Converted to pixels |
| Font colour + opacity | |
| Bold / italic | |
| Buffer size + colour | Rendered as CSS `text-shadow` approximation |

Labels are rendered as permanent Leaflet tooltips. A **collision-detection pass** runs after each zoom/pan event (`moveend`/`zoomend`) using `getBoundingClientRect`; overlapping labels are hidden (greedy first-wins). This keeps the map readable at small scales without SVG overhead.

Per-layer label visibility can be toggled from the legend cog menu.

---

## 7. Interactive features in the exported HTML

### 7.1 Legend / layer control

- Collapsible legend panel (right side).
- Layer groups match the QGIS layer tree; group headers have a visibility checkbox that toggles all child layers.
- Each layer row shows a colour swatch (or categorised swatches), visibility checkbox, and a ⚙ cog button.
- Cog panel contains an **opacity slider** (0–100 %) and a **Labels on/off** toggle (only shown if the layer has labels).

### 7.2 Feature info panel

A small floating panel (bottom-right ℹ button). Clicking any map feature shows its attribute table. Hidden by default.

**Stacked/overlapping features**: a unified map-level click handler collects all features within 10 px of the click. If more than one is found, a numbered pick-list is shown; clicking an entry drills into that feature's attributes with a ‹ Back button.

### 7.3 Attribute table panel

A bottom drawer (≡ button, top-left). Contains:
- Layer dropdown — switch between exported layers.
- Sortable table — click any column header to sort ascending/descending (▲/▼).
- Click any row — zooms to that feature and opens its info in the info panel.

### 7.4 Themes dropdown

Only visible when themes were defined at export time. A `— Themes —` `<select>` control in the top-right corner. Selecting a theme:
1. Sets each layer's visibility to the saved state.
2. Flies the map to the saved extent (if one was captured).

### 7.5 Filter toolbar

Pinned to the top of the legend panel. Pick a layer → pick an attribute → select one or more values (or type a substring). The map live-filters to matching features. A feature count badge updates in real time.

### 7.6 Minimap

A small overview minimap (bottom-right corner) using the same OSM tile source. Can be toggled open/closed.

### 7.7 Context menu

Right-clicking the map provides: **Centre map here**, **Zoom in/out**, **Copy lat,lon**.

### 7.8 Fullscreen

A fullscreen toggle button (top-left) using the Leaflet.fullscreen plugin.

### 7.9 Basemap

OpenStreetMap is always included. Zoom is unrestricted up to level 23 (tiles over-scale above their native level 19).

---

## 8. Branding

The map header shows a logo. Resolution order:

1. `qgis_webmap/vendor/logo.svg` — embedded as inline SVG (preferred).
2. `qgis_webmap/vendor/logo.png` — embedded as base64 data URI.
3. Built-in fallback SVG globe icon.

---

## 9. Initial map extent

The plugin captures the QGIS canvas extent when the dialog opens (before any user interaction). This extent (re-projected to WGS-84) is baked into the HTML as the initial `fitBounds` call. If the export contains features but no canvas extent was captured, the map auto-fits to the data extent instead.

---

## 10. Offline behaviour

All JavaScript and CSS (Leaflet core, fullscreen, minimap, contextmenu) are embedded inline from the `vendor/` folder at export time. File-based layers (GeoJSON, raster) are also embedded. The resulting HTML works with no internet access.

WMS, XYZ tile layers, and the OSM basemap do require internet access at view time.
