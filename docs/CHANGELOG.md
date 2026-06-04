# Changelog — QGIS Web Map Exporter

## Development session log

All entries below represent work completed in a single extended development session building out the plugin from its initial state.

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
