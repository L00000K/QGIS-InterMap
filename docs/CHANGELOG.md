# Changelog — QGIS Web Map Exporter

## Development session log

All entries below represent work completed in a single extended development session building out the plugin from its initial state.

---

### Session — 2026-07-22 · Line symbology & curved labels (v1.6.0)

Reported from a QGIS map that exported with the wrong line rendering: cased
roads collapsed to a single stroke, a hashed/tick line came through as a
plain line, and line labels sat flat at the centroid instead of following
the line.

#### Cased / multi-stroke lines

`_extract_symbol_style` walked line symbol layers but returned on the first
one, so only one stroke of a layered line survived. It now walks **all**
layers into an ordered `strokes[]` list (bottom→top); the web app stacks one
non-interactive canvas "casing" underlay per lower stroke beneath the
interactive core, reproducing QGIS's layered line symbology (e.g. a coloured
core over a wider casing). The legend swatch uses the top/core stroke.

#### Marker / hashed (tick) lines

`QgsMarkerLineSymbolLayer` / `QgsHashedLineSymbolLayer` (markers or ticks
repeated along a line) are exported as `tick` strokes — colour from the
sub-symbol, plus interval and tick length. They can't be a Leaflet dash, so
the web app draws them as perpendicular hash marks in a container-space SVG
overlay, re-projected on every move/zoom.

#### Curved line labels

Line labels now follow the line via SVG `<textPath>` built from the line's
projected pixel path (with above/on/below placement, halo via
`paint-order`, and left-to-right reading correction), rendered in a
dedicated overlay group that the point-label relayout can't disturb —
instead of the previous flat centroid text.

Verified end-to-end in headless Chromium against a fixture with a cased line
and a tick line: the export draws two stacked strokes for the cased line,
seven perpendicular ticks for the marker line, and two curved textPath
labels, with no JS errors. 77 unit tests (six new for line-stroke
extraction and payload survival).

---

### Session — 2026-07-17 · PDF report mode (v1.5.0)

#### Feature: scroll a PDF, drive the map

The report pane can now show a **PDF** instead of markdown. In the dialog's
Report section, pick a `.pdf` and add **page → map view bindings**; the
exported page renders the PDF page-by-page down the left-hand pane (via a
bundled PDF.js — fully offline, worker included as an inline blob), and as
the reader scrolls, whichever page sits in front of them becomes current:
its bound map view is applied through the same `applyView` machinery as
markdown scrollytelling (2D fly-to or 3D camera). Bound pages carry a small
"◎ view" chip, the Contents list shows `Page N — View` entries with the
current page highlighted, and the header shows `p.N/total`. The
resizable divider and collapse-to-full-map behaviour are shared with
markdown mode; when both a PDF and a markdown report are configured, the
PDF wins.

Export-side validation warns on bindings to unknown views, pages beyond the
document, and malformed page numbers (`_build_pdf_report_payload`, with a
best-effort raw page count). Verified end-to-end in headless Chromium:
scrolling from page 1 to page 3 flies the map from the Overview extent
(zoom 11) to the North-detail extent (zoom 14) with zero JS errors.

Pages **lazy-render**: all holders are laid out immediately (so scroll
geometry and the view driver work from the start) but pixels are only
painted when a page nears the viewport (IntersectionObserver, 1200 px
margin) — verified with a 40-page document where page 35 stays blank until
scrolled to. Bindings also accept an **options** string using the
`:::view` grammar (`3d pitch=-35 heading=120`), parsed at export into the
opts dict `applyView()` already understands, so a page can put the 3D
camera at a specific angle.

---

### Session — 2026-07-16 · Bottom-up rebuild (v1.4.0)

#### Restructure: exporter monolith → package

`exporter.py` had grown to 7,682 lines, 5,600 of which were a single f-string containing the whole web application. It is now `intermap/exporter/` — thirteen focused Python modules plus `templates/`, where the exported page lives as ordinary HTML/CSS/JS files (`head.html`, `webmap.css`, `body.html`, `app.js`, `cesium.js`, `report.js`) with `@@placeholder@@` substitution. The public API (`from .exporter import WebMapExporter`) is unchanged.

The restructure was proven safe mechanically: `tests/render_snapshot.py` rendered four representative export configurations before and after the split, and the SHA-256 hashes matched byte-for-byte.

#### Fix: report / story mode was completely broken

Embedding `marked.min.js` with a blanket `.replace("</", "<\\/")` corrupted regex literals inside the library (e.g. `/^</` became an unterminated regex), so the whole script block failed to parse and the report pane rendered nothing. New `_script_safe_js()` escapes only `</script` (the only sequence that can terminate a script element), applied to marked and all Leaflet plugin bundles. Verified in headless Chromium: the report now renders headings, TOC, figures, and working `view:`/`gis:` links.

#### Testing: suite now tests the real code

The old test file asserted against *copies* of exporter functions pasted into the test module, so it could pass while the plugin was broken. Replaced with `tests/test_exporter.py` (55 tests) which imports the actual modules via `tests/qgis_mock/`, plus `tests/browser_check.py`, which boots rendered exports in headless Chromium and fails on any JS error.

#### Cleanup: dead code removed

Nine unused theme-token locals and their theme dict entries, five orphaned dialog methods (legacy config-instance loaders, pre-SVG rich-text helper), duplicate inline imports, four unused Qt imports, and CSS rules for UI that no longer exists (old tooltip-based labels, old multi-feature pick list, `.fading` media state). DOM-structure probes before/after confirm no behavioural change.

---

### Session — 2026-06-01

#### Fix: Marker shape rendering restored

The `L.divIcon` SVG path for non-circle marker shapes had been dropped, causing all non-circle points to fall back to the default Leaflet pin marker. Restored the `shapeSvgInner()` function handling all 10 shape types.

Shapes supported: `circle`, `square`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`, `star`, `cross`, `x`.

---

#### Feature: Label extraction from QGIS

Added `_extract_label_config()` which reads `QgsPalLayerSettings` from a layer's labelling engine and extracts: field name, is-expression flag, enabled state, font family/size/colour/bold/italic, and buffer halo settings. Labels are rendered as permanent Leaflet tooltips on dedicated per-layer panes with `pointerEvents: none`.

Font family names are appended with `, Arial, sans-serif` to ensure readable fallback in browsers where the QGIS font is not installed.

---

#### Feature: Per-layer cog settings panel in legend

Each layer row in the legend now has a ⚙ cog button that expands an inline panel with:
- **Opacity slider** (0–100 %)
- **Labels on/off toggle** (only shown when labels are present)

---

#### Change: OSM basemap always included

Removed the "include basemap" checkbox from the dialog. The OSM tile layer is now always present, as the map is designed to always have geographic context.

---

#### Feature: SVG logo support

The map header logo now prefers `vendor/logo.svg` (embedded inline) over `vendor/logo.png` (embedded as base64 data URI) over a built-in fallback SVG globe icon.

---

#### Fix: Marker stroke opacity

Added `markerStrokeOpacity` to the Python style extraction. This value is passed through to the SVG `stroke-opacity` attribute. Outline-only markers (transparent fill, coloured stroke) now correctly render their stroke at minimum 0.5 px width.

---

#### Change: Info panel replaces sidebar and popups

Removed the sidebar-v2 dependency and `bindPopup` calls. All feature attribute display now goes through a lightweight `#info-panel` floating div. Triggered by a small ℹ button in the bottom-right corner.

---

#### Feature: Layer tree / groups in legend

The QGIS layer tree (including nested groups) is now reflected in the legend. Groups appear as collapsible bold headers. Each group has a checkbox that toggles all its child layers simultaneously.

The tree structure is serialised to the `LAYER_TREE` JS variable at export time.

---

#### Feature: Label collision detection

A greedy first-wins collision detection pass runs on every `moveend` / `zoomend` event and once 150 ms after initial render. Uses `getBoundingClientRect` — no additional layout engine required. Overlapping labels are hidden but remain in the DOM so they can reappear if the viewport changes.

---

#### Feature: Initial map extent from QGIS canvas

When the export dialog opens, the current QGIS canvas extent is captured (re-projected to WGS-84) and stored. The exported HTML `fitBounds` to this extent on load, so the viewer sees the same area the analyst was looking at.

---

#### Feature: Layer groups in plugin dialog

The Layers tab now walks the QGIS layer tree recursively. Layer groups appear as non-checkable grey header items (`▸ Group Name`) with child layers indented beneath them. This matches the appearance of the QGIS Layers panel.

---

#### Feature: Multi-feature click with pick-list

A unified map-level click handler replaces per-layer click handlers. Clicking collects all vector features within 10 px:

- **1 feature** → attributes shown directly in the info panel.
- **Multiple features** → a numbered pick-list is shown; clicking an item drills into that feature's attributes with a ‹ Back button.

This correctly handles overlapping/coincident points which are very common in survey and GPS data.

---

#### Feature: Attribute table panel

A bottom drawer panel (≡ button, top-left) shows all features for a selected layer in a sortable table. Clicking a row zooms to that feature and opens its attributes in the info panel. Column headers are clickable to sort ascending/descending.

---

#### Feature: Themes (optional named layer presets)

A second tab in the plugin dialog allows defining named themes. Each theme records:
- Name + notes
- Layer visibility snapshot
- Optional map extent (captured from the QGIS canvas)

Themes are exported as the `THEMES` JS array. A `— Themes —` dropdown control appears in the map top-right only when `THEMES.length > 0`. Selecting a theme sets layer visibility and zooms to the saved extent.

---

#### Fix: Max zoom level

The map was capped at OSM's native tile zoom of 19. Changed to `maxNativeZoom: 19, maxZoom: 23` on the tile layer and `maxZoom: 23` on the map itself. Tiles are now over-scaled (upsampled) by Leaflet above level 19, allowing detailed inspection of data.

---

#### Change: Scenes renamed to Themes

Based on user feedback, the "Scenes" concept was renamed to "Themes" throughout the plugin dialog and exported HTML to better match the intended use (preset layer combinations for a thematic map viewer). The side-panel UI was also replaced with a compact inline dropdown control.

---

## Version history

| Version | Date | Notes |
|---|---|---|
| 1.0.0 | Initial | Basic vector/raster/WMS export, single/categorised/graduated renderers, legend toggle |
| 1.1.0 | 2026-06-01 | Shape markers, labels, cog settings, groups, collision detection, initial extent |
| 1.2.0 | 2026-06-01 | Multi-feature click, attribute table, themes, zoom fix |
