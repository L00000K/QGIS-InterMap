# Task List — QGIS Web Map Exporter

## Status key

| Symbol | Meaning |
|---|---|
| ✅ | Completed and pushed |
| 🔜 | Planned / next up |
| ⏸ | Blocked (dependency or decision required) |
| ❌ | Deferred (out of scope for now) |

---

## Completed ✅

### PDF report mode (2026-07-17)

- [x] Vendor PDF.js legacy build (`pdfjs.min.js` + worker) for offline rendering
- [x] `_build_pdf_report_payload`: base64 PDF, page→view bindings, validation warnings
- [x] Web pane renders PDF pages as canvases; scroll drives bound map views
- [x] TOC page list with current-page highlight; header page indicator; view chips
- [x] Dialog: PDF picker + page/view bindings table, persisted in configs
- [x] Unit + headless-browser tests (scroll page 1→3 verifiably flies the map)

### Bottom-up rebuild (2026-07-16)

- [x] Split `exporter.py` monolith into `intermap/exporter/` package (13 modules + `templates/`)
- [x] Extract the 5,600-line embedded HTML f-string into real HTML/CSS/JS template files
- [x] Prove the restructure byte-identical via snapshot hashes (4 export configurations)
- [x] Fix report mode: embedded marked.min.js corrupted by blanket `</` escaping
- [x] Rewrite tests to import the real modules through a qgis mock (55 tests)
- [x] Add headless-Chromium boot checks for rendered exports
- [x] Remove dead Python/CSS accumulated across the app's evolution

### Core export

- [x] Export vector layers as embedded GeoJSON with Leaflet styles
- [x] Export raster layers as base64-encoded PNG image overlays
- [x] Export WMS/WMTS/XYZ tile layers as live Leaflet tile layers
- [x] Single symbol renderer support (fill, stroke, opacity)
- [x] Categorised renderer support (per-category colour map)
- [x] Graduated renderer support (per-range colour map)
- [x] Rule-based renderer support (first-match fallback)
- [x] Line dash pattern translation (solid/dash/dot/dash-dot/dash-dot-dot/custom)

### Marker shapes

- [x] Restore `L.divIcon` SVG rendering for non-circle marker shapes
- [x] Support: circle, square, diamond, triangle, pentagon, hexagon, octagon, star, cross, x
- [x] Marker stroke opacity (`markerStrokeOpacity`) passed through to SVG `stroke-opacity`
- [x] Minimum 0.5 px stroke for outline-only shapes (NoPen fill)
- [x] Marker rotation via SVG `transform="rotate()"`

### Labels

- [x] Extract label config from `QgsPalLayerSettings` (field, font, size, colour, bold/italic)
- [x] Extract buffer/halo settings (size, colour)
- [x] Export labels as permanent Leaflet tooltips on dedicated label panes
- [x] Per-layer label pane with `pointerEvents: none` (labels don't intercept clicks)
- [x] Font fallback: append `, Arial, sans-serif` to QGIS font family names
- [x] Greedy label collision detection — hides overlapping labels, re-runs on zoom/pan
- [x] Per-layer label on/off toggle in legend cog settings

### Legend / layer control

- [x] Collapsible legend panel with OSM basemap row
- [x] Layer groups (collapsible headers matching QGIS layer tree)
- [x] Group visibility checkbox (toggles all child layers)
- [x] Per-layer visibility checkbox
- [x] Per-layer colour swatch (single or categorised)
- [x] Per-layer cog (⚙) settings panel with opacity slider
- [x] Labels toggle in cog panel (only shown when layer has labels)

### Map UI

- [x] Replace sidebar-v2 with lightweight floating `#info-panel`
- [x] Remove `bindPopup` — all feature info through info panel
- [x] Multi-feature click: collect all features within 10 px, show pick-list, drill into attributes with Back button
- [x] Attribute table panel (bottom drawer): layer dropdown, sortable columns, row click → zoom + info
- [x] Filter toolbar: layer → field → value (multi-select or text); live feature count
- [x] Minimap (bottom-right, collapsible)
- [x] Context menu (right-click): centre, zoom in/out, copy lat,lon
- [x] Fullscreen toggle
- [x] Scale bar

### Themes

- [x] Themes tab in plugin dialog (Add / Edit / Delete / Up / Down)
- [x] Theme form: name, notes, capture QGIS extent button
- [x] Theme saves layer visibility snapshot from Layers tab
- [x] Themes exported as `THEMES` JSON array in HTML
- [x] Themes dropdown control (top-right) — only rendered when `THEMES.length > 0`
- [x] Applying a theme sets layer visibility and zooms to saved extent

### Basemap / extent

- [x] Always include OSM basemap (no toggle)
- [x] Map `maxZoom: 23`, OSM `maxNativeZoom: 19` (tiles over-scale above level 19)
- [x] Capture QGIS canvas extent at dialog open time; use as initial `fitBounds`

### Branding

- [x] SVG logo support: `vendor/logo.svg` → `vendor/logo.png` → built-in fallback
- [x] Logo embedded inline (SVG) or as base64 data URI (PNG)

### Dialog (QGIS side)

- [x] Layer tree shown with group headers (non-checkable) and indented child layers
- [x] Pre-check layers that are selected in QGIS Layers panel
- [x] Two-tab dialog: Layers + Themes
- [x] Capture-extent button in Themes tab stores WGS-84 bounds

### Testing

- [x] 18 offline unit tests (no QGIS install required)
- [x] Tests cover: colour conversion, geometry flattening, GeoJSON structure, style serialisability, HTML output, unit conversion, shape aliases, WMS layer defs

---

## Backlog audit (2026-07-17)

Every pending/deferred item below was checked against the current code.
Items marked ✅ were implemented in later sessions; items marked ⤳ were
superseded by a different mechanism that covers the same need.

### Completed since originally listed ✅

- [x] Cluster / spiderify toggle — `markercluster.js/.css` are vendored and wired
  (`spiderfyOnMaxZoom` in `app.js`), alongside the runtime explode/group system
  for point layers
- [x] Attribute table search box — `#attr-table-search` live-filters rows
- [x] Export table to CSV — `#attr-table-csv` button
- [x] Highlight selected feature on map — `highlightFeatureOnMap()` on row click
- [x] Graduated renderer range labels — `styles.py` exports
  `r.label() or "lower – upper"` per range and the legend renders entry labels
- [x] Print / export to image (was deferred) — `#print-btn` uses the browser
  print pipeline; report mode adds inline print copies of figures

### Superseded by app direction ⤳

- Label leader lines → the icon de-overlap **spread system** draws leader
  lines from spread icons back to their true position (`#spread-leader-svg`)
- Point displacement renderer → same spread/explode system covers overlapping
  point separation at runtime for any point layer, without a QGIS renderer
- Virtual DOM / canvas label rendering → labels moved from per-tooltip DOM to
  a **single-SVG render pass** with collision detection; a canvas rewrite is
  no longer the natural next step (see Performance below for what remains)

### Still pending 🔜

- [ ] QGIS label x/y offset support — labels still placed at centroid;
  `QgsPalLayerSettings` offsets are not read (`labels.py` has no offset fields)
- [ ] Heatmap renderer → Leaflet.heat (would need `leaflet-heat.js` vendored)
- [ ] Inverted polygon renderer (mask/highlight)
- [ ] Custom legend title field in plugin dialog
- [ ] GeoJSON simplification at export time for large polygon layers
  (Douglas-Peucker) — still relevant for the "very large layers" limitation
- [ ] Label performance for > 10 000 features — the SVG pass helps, but very
  large datasets still do a full placement recompute per zoom/pan

---

## Deferred ❌

### CRS / coordinate system export

- User confirmed: "Don't worry about this one for now."
- All data is currently re-projected to WGS-84 (EPSG:4326) at export time, which is what Leaflet expects.

### Layer info button (per-layer metadata popover)

- Was considered but not selected by the user during feature prioritisation.
- Would show layer description / metadata in a popover when an ℹ icon next to the layer name is clicked.
- Still absent from the current legend UI (verified 2026-07-17).

---

## Known limitations

| Limitation | Notes |
|---|---|
| Expression-based labels | Field name is exported, but QGIS expressions (e.g. `"NAME" \|\| ' (' \|\| "POP" \|\| ')'`) are not evaluated in the browser |
| Data-defined symbology | Per-feature overrides (data-defined size, rotation, etc.) are not yet captured |
| Raster styling | Raster colour ramps, hillshading, etc. are baked into the exported PNG but cannot be toggled |
| Very large layers | Embedding 100k+ features as GeoJSON produces large files and slow browsers |
| SVG marker rotation | Applied via SVG `transform` — may not precisely match QGIS rotation for complex shapes at non-cardinal angles |
