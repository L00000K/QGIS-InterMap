# InterMap

A QGIS 3 plugin that exports selected layers to a **standalone HTML web map** powered by [Leaflet.js](https://leafletjs.com). Symbology, labels, layer groups, and interactive features are all preserved in a single self-contained `.html` file — no server required.

---

## Feature highlights

| Category | What's included |
|---|---|
| **Layer types** | Vector (point/line/polygon), raster image overlays, WMS/WMTS/XYZ tile layers |
| **Symbology** | Single, categorised, graduated, rule-based renderers; 11 marker shapes; dash patterns; fill/stroke opacity |
| **Labels** | Font, size, colour, bold/italic, buffer halo, collision detection, per-layer toggle |
| **Legend** | Layer groups (collapsible), visibility checkboxes, opacity sliders, per-layer cog settings |
| **Feature info** | Click any feature → floating info panel; stacked/overlapping points show a numbered pick-list |
| **Attribute table** | Bottom panel with sortable columns; click row to zoom + highlight feature |
| **Themes** | Save named layer-visibility + extent presets; switch via dropdown in the map |
| **Filter toolbar** | Filter by layer → attribute → value (multi-select or free text); live feature count |
| **Basemap** | OpenStreetMap always included; zoom up to level 23 (tiles over-scale gracefully) |
| **Offline** | Leaflet and all vendor JS/CSS are embedded inline; file-based layers work with no internet |

---

## Requirements

- QGIS 3.0 or later

## Installation

```bash
python3 install_plugin.py
```

Then in QGIS: **Plugins → Manage and Install Plugins → Installed → Enable "InterMap"**.

Manual install — copy the `intermap/` folder to your QGIS plugins directory:

| Platform | Path |
|---|---|
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/` |
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` |

## Usage

1. Open a QGIS project with one or more layers.
2. In QGIS go to **Web → InterMap → Export to Web Map…**
3. **Layers tab** — check the layers to export; the layer tree order is preserved.
4. *(Optional)* **Themes tab** — define named themes (visibility presets + extent).
5. Choose an output `.html` file path and click **Export**.
6. Open the generated file in any modern browser.

## Branding / logo

Place either `vendor/logo.svg` or `vendor/logo.png` inside the `intermap/` folder. The plugin embeds it inline in the map header. If neither file is present a built-in fallback SVG is used.

## Documentation

| Document | Contents |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Full plugin specification |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical architecture and code map |
| [docs/FEATURES.md](docs/FEATURES.md) | Feature-by-feature reference |
| [docs/TASKS.md](docs/TASKS.md) | Development task list (completed, pending, deferred) |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Development history |

## Running tests

```bash
python3 -m pytest intermap/test_exporter_logic.py -v
```

All 18 tests run without a QGIS installation (QGIS APIs are mocked).

## Plugin structure

```
intermap/
├── __init__.py              QGIS entry point
├── metadata.txt             Plugin metadata
├── plugin.py                Plugin class (menu/toolbar wiring)
├── dialog.py                Export dialog (Layers tab + Themes tab)
├── exporter.py              Core export logic: symbology, GeoJSON, HTML template
├── icon.png                 Toolbar icon
├── test_exporter_logic.py   Offline unit tests
└── vendor/                  Embedded JS/CSS libraries
    ├── leaflet.js / .css
    ├── leaflet.fullscreen.*
    ├── leaflet.minimap.*
    ├── leaflet.contextmenu.*
    ├── logo.svg              (optional — your branding)
    └── logo.png              (optional — fallback branding)
```
