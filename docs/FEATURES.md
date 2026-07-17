# Feature Reference — QGIS Web Map Exporter

## 1. Layer export

### Vector layers

Point, line, and polygon vector layers are exported as embedded GeoJSON. Each feature's geometry and all attribute fields are preserved. Symbology is read from the QGIS renderer at export time and translated to equivalent Leaflet styles.

**Supported renderers:**

| Renderer | How it works |
|---|---|
| Single symbol | One style applied to every feature |
| Categorised | A `styleMap` dict keyed by the categorisation field value |
| Graduated | A `styleMap` dict; each range gets a sentinel key; features are matched at render time by value comparison |
| Rule-based | First rule wins; the rule's symbol is translated; falls back to `__default__` |

### Raster layers

Exported as a base64-encoded PNG image overlay (using QGIS's `QgsMapRendererParallelJob`). The raster is clipped to its extent and positioned accurately with `L.imageOverlay`. The file remains self-contained.

### WMS / WMTS / XYZ tile layers

These are not embedded — they are re-streamed from their source URL at view time using `L.tileLayer.wms` or `L.tileLayer`. Requires internet access when the HTML is opened.

---

## 2. Marker shapes

All shapes support: fill colour, fill opacity, stroke colour, stroke opacity, stroke width, rotation.

| Shape name | Rendered as |
|---|---|
| `circle` | `L.circleMarker` (canvas, anti-aliased) |
| `square` | SVG `<rect>` |
| `diamond` | SVG `<polygon>` (rotated square) |
| `triangle` | SVG `<polygon>` (equilateral) |
| `pentagon` | SVG `<polygon>` |
| `hexagon` | SVG `<polygon>` |
| `octagon` | SVG `<polygon>` |
| `star` | SVG `<polygon>` (5-point) |
| `cross` | SVG `<line>` pair |
| `x` | SVG `<line>` pair (45° rotated cross) |

Shapes are rendered inside a `L.divIcon` containing a tiny inline SVG sized to the marker footprint. The icon anchor is centred. Rotation is applied via SVG `transform="rotate(...)"`.

**Outline-only markers** (NoPen fill): `markerStrokeWidth` is set to at least 0.5 px even when fill is transparent, so the outline is always visible.

---

## 3. Labels

Labels are exported when `QgsPalLayerSettings` is configured on a layer. The following properties are translated:

| QGIS property | Web map equivalent |
|---|---|
| Field / expression | Leaflet tooltip content |
| Font family | CSS `font-family` (with `, Arial, sans-serif` appended as fallback) |
| Font size | CSS `font-size` in px |
| Font colour | CSS `color` |
| Bold / italic | CSS `font-weight` / `font-style` |
| Text buffer (halo) | CSS `text-shadow` approximation |
| Enabled state | Initial visibility of label pane |

### Collision detection

After each zoom or pan, a greedy first-wins pass runs across all visible label elements:

- Uses `getBoundingClientRect` to get actual rendered positions.
- Labels are compared with 3 px padding between them.
- Overlapping labels are hidden (`visibility: hidden`) — they remain in the DOM so they can reappear if the view changes.
- The pass re-runs on `moveend` and `zoomend`, and once 150 ms after initial render.

This keeps the map legible at small scales without the overhead of a full label engine.

### Per-layer toggle

The ⚙ cog menu in the legend provides a **Labels** on/off toggle for each layer. Turning labels off hides the entire label pane. Turning them back on re-runs collision detection.

---

## 4. Legend / layer control

The legend panel (collapsible, right side) mirrors the QGIS layer tree:

- **Groups** — shown as bold headers with a group visibility checkbox. Toggling the group checkbox shows/hides all child layers simultaneously.
- **Layers** — each row shows:
  - Visibility checkbox
  - Colour swatch (single colour, or a mini-grid of category colours)
  - Layer name
  - ⚙ cog button

### Cog settings panel

Clicking ⚙ expands an inline settings panel beneath the layer row:

- **Opacity slider** — 0–100 %, updates the Leaflet layer opacity in real time.
- **Labels toggle** — only shown when the layer has exported labels.

---

## 5. Feature info panel

A small floating panel triggered by the ℹ button (bottom-right). Hidden by default.

Clicking any vector feature opens the panel with a two-column attribute table (field name / value). All attributes from `feature.properties` are shown.

### Stacked / overlapping features

A single map-level click handler (not per-layer) collects all vector features within 10 px of the click point. This correctly handles:

- Points at exactly the same location (common in surveys, GPS tracks).
- Points that overlap at the current zoom level even if not coincident.

**One feature found** → attributes shown immediately.

**Multiple features found** → a numbered pick-list is shown:

```
2 features at this location
  1. Road Centreline
  2. Road Centreline
```

Clicking a list item drills into that feature's attributes. A **‹ Back** button returns to the pick-list. The Back button shows how many features were found, so the user is never lost.

---

## 6. Attribute table

Opened with the ≡ button (top-left control). A bottom drawer panel (240 px height) showing all features for one layer at a time.

- **Layer selector** — dropdown of all exported vector layers.
- **Sortable columns** — click any column header to sort ascending (▲), click again for descending (▼), click again to reset.
- **Row click** — zooms to that feature's extent (with `maxZoom: 16`) and opens the feature's attributes in the info panel.

---

## 7. Themes

Themes let the map author pre-configure named "views" of the map — different combinations of visible layers and/or extents — that a viewer can switch between using a dropdown.

### Defining themes (in QGIS)

1. Open the plugin dialog.
2. Go to the **Themes** tab.
3. Click **＋ Add** to start a new theme.
4. Enter a **Name** (required).
5. Optionally enter **Notes** (shown as a subtitle in the dropdown).
6. In the **Layers** tab, check/uncheck the layers that should be visible for this theme. Return to the Themes tab.
7. Optionally click **📷 Capture current QGIS view** to store the map extent.
8. Click **Save theme**.
9. Repeat for additional themes.
10. Use **↑ Up / ↓ Down** to reorder. Select a theme and click **✎ Edit** or **✕ Delete** to modify.

### Using themes (in the browser)

If at least one theme was defined, a **`— Themes —`** dropdown appears in the top-right corner of the map. Selecting a theme instantly:

1. Shows/hides each layer to match the saved visibility state.
2. Flies the map to the saved extent (if one was captured).

If no themes were defined, the dropdown is absent entirely.

---

## 8. Filter toolbar

Located at the top of the legend panel. Controls:

1. **Layer selector** — which layer to filter.
2. **Field selector** — which attribute field to filter on.
3. **Value selector** — multi-select list of unique values; or a text box for substring matching.

Matching logic:
- Feature properties are compared against selected values or the search string.
- Non-matching features are hidden from the map.
- A **count badge** shows `n / total features`.
- Selecting no values = show all.

---

## 9. Basemap and zoom

OpenStreetMap is always included as the base tile layer (attribution included per OSM terms). It cannot be toggled off, as the map is designed to always have geographic context.

| Zoom behaviour | Value |
|---|---|
| OSM native tile zoom cap | 19 |
| Map max zoom | 23 |
| Behaviour above level 19 | Tiles are over-scaled (upsampled) by Leaflet |

This means you can zoom very close into your data even in areas where OSM tiles stop at level 18–19.

---

## 10. Minimap

A small overview map in the bottom-right corner (Leaflet.minimap). Uses the same OSM tile source. The minimap shows a grey rectangle representing the main map's current viewport. Can be collapsed by clicking its toggle button.

---

## 11. Context menu

Right-click anywhere on the map:

| Option | Action |
|---|---|
| Centre map here | Pans to the clicked point |
| Zoom in | `map.zoomIn()` |
| Zoom out | `map.zoomOut()` |
| Copy lat, lon | Copies `lat, lng` to clipboard (6 decimal places) |

---

## 12. Initial extent

When the export dialog opens, the current QGIS canvas extent is captured and converted to WGS-84. The exported HTML `fitBounds` to this extent on load, so the user opens the map seeing exactly what they saw in QGIS.

If the extent cannot be captured (e.g. no canvas is open), the map auto-fits to the combined data extent of all exported layers.

---

## 13. Branding / logo

The map header shows a logo in the top bar. Place files in `intermap/vendor/`:

| File | Used when |
|---|---|
| `logo.svg` | Present (preferred — scalable, embedded inline) |
| `logo.png` | `logo.svg` absent (embedded as base64 data URI) |
| Built-in fallback | Neither file present |

---

## 14. Offline behaviour

| Asset | Offline? |
|---|---|
| Leaflet JS + CSS | ✅ Embedded from `vendor/` |
| Fullscreen / minimap / contextmenu plugins | ✅ Embedded |
| GeoJSON feature data | ✅ Embedded |
| Raster layer image | ✅ Embedded as base64 |
| OSM basemap tiles | ❌ Requires internet |
| WMS / XYZ tile layers | ❌ Requires internet |
