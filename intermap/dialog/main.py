"""WebMapExportDialog: dock-widget shell, settings, header, tab switching."""
import os
import datetime
from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QFrame, QStackedWidget,
)
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtCore import Qt, QStandardPaths, QSettings
from qgis.core import (
    QgsProject, QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsRectangle,
)

from .richtext import RichTextMixin
from .configs import ConfigsMixin
from .info_tab import MapInfoTabMixin
from .views_tab import MapViewsTabMixin
from .layers_tab import LayersTabMixin
from .lite import LiteModeMixin
from .export_tab import ExportTabMixin



# ── Drag-to-draw extent tool ──────────────────────────────────────────────────

# ── Vertical resize handle for rich-text editors ─────────────────────────────
from .constants import _SETTINGS_KEY, _PURPLE, _PURPLE_DARK, _PURPLE_LIGHT


class WebMapExportDialog(RichTextMixin, ConfigsMixin, MapInfoTabMixin,
                         MapViewsTabMixin, LayersTabMixin, LiteModeMixin,
                         ExportTabMixin, QDockWidget):
    """Dockable InterMap export panel."""

    # tab indices used by _switch_tab / _set_mode
    _MAP_VIEWS_TAB = 1
    _LITE_TAB = 4

    def __init__(self, iface, parent=None):
        super().__init__("InterMap", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("InterMapPanel")
        self.setMinimumWidth(420)
        self._initial_extent = self._capture_canvas_extent()
        self._map_views = []
        self._changelog = []
        self._is_lite = False
        self._lite_extent = None
        self._editing_map_view_idx = None
        self._editing_map_view_extent = None
        self._loaded_instance_name = None
        self._has_unsaved_changes = False
        self._mv_rubber_bands = {}
        self._mv_draw_tool = None
        self._build_ui()
        self._update_initial_extent_label()
        self.path_edit.setText(self._default_output_path())
        self._populate_layers()
        self._load_settings()

    def closeEvent(self, event):
        self._mv_clear_rubber_bands()
        self._save_settings()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # Only show rubber bands when actually on the Map Views tab
        if self._tab_stack.currentIndex() != self._MAP_VIEWS_TAB:
            self._mv_clear_rubber_bands()

    def hideEvent(self, event):
        self._mv_clear_rubber_bands()
        super().hideEvent(event)

    def _on_close_clicked(self):
        self._mv_clear_rubber_bands()
        self._save_settings()
        self.hide()

    def _capture_canvas_extent(self):
        try:
            canvas = self.iface.mapCanvas()
            ext = canvas.extent()
            src_crs = canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(ext)
            return [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
        except Exception:
            return None

    def _wgs84_to_canvas_rect(self, ext):
        """Convert [[s,w],[n,e]] WGS-84 extent to QgsRectangle in canvas CRS."""
        canvas = self.iface.mapCanvas()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = canvas.mapSettings().destinationCrs()
        tr = QgsCoordinateTransform(wgs84, canvas_crs, QgsProject.instance())
        rect = QgsRectangle(ext[0][1], ext[0][0], ext[1][1], ext[1][0])
        return tr.transformBoundingBox(rect)

    def _default_output_path(self):
        downloads = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        if not downloads or not os.path.isdir(downloads):
            downloads = os.path.expanduser("~")
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        project_name = QgsProject.instance().baseName() or "webmap"
        safe_name = "".join(
            c if c.isalnum() or c in " _-." else "_" for c in project_name
        ).strip() or "webmap"
        return os.path.join(downloads, f"{ts} - {safe_name}.html")

    def _load_settings(self):
        s = QSettings()
        for flag, attr in (
            ("include_layer_control", "layer_control_cb"),
            ("include_basemap",       "basemap_cb"),
            ("include_info",          "include_info_cb"),
            ("include_project_info",  "include_project_info_cb"),
            ("include_doc_metadata",  "include_doc_metadata_cb"),
            ("include_doc_control",   "include_doc_control_cb"),
            ("feat_identify",         "feat_identify_cb"),
            ("feat_attr_table",       "feat_attr_table_cb"),
            ("feat_attr_csv",         "feat_attr_csv_cb"),
            ("feat_attr_geojson",     "feat_attr_geojson_cb"),
            ("feat_measure",          "feat_measure_cb"),
            ("feat_filter",           "feat_filter_cb"),
            ("feat_search",           "feat_search_cb"),
            ("feat_minimap",          "feat_minimap_cb"),
            ("feat_fancy_labels",     "feat_fancy_labels_cb"),
            ("feat_changelog",        "feat_changelog_cb"),
            ("feat_3d",               "feat_3d_cb"),
            ("feat_sketch",           "feat_sketch_cb"),
        ):
            key = f"{_SETTINGS_KEY}/{flag}"
            if s.contains(key):
                getattr(self, attr).setChecked(s.value(key, True, type=bool))

        for _3d_key, _3d_attr in (
            ("cesium_ion_token",   "cesium_ion_token_edit"),
            ("google_maps_key",    "google_maps_key_edit"),
            ("extrude_field",      "extrude_field_edit"),
            ("cog_proxy",          "cog_proxy_edit"),
            ("report_md_path",     "report_md_edit"),
            ("report_figures_dir", "report_figures_edit"),
        ):
            val = s.value(f"{_SETTINGS_KEY}/{_3d_key}", "")
            if val:
                getattr(self, _3d_attr).setText(val)
        _es = s.value(f"{_SETTINGS_KEY}/extrude_scale", None)
        if _es is not None:
            try: self.extrude_scale_spin.setValue(float(_es))
            except Exception: pass
        _er_id = s.value(f"{_SETTINGS_KEY}/elevation_raster_id", "")
        if _er_id:
            idx = self.elevation_raster_combo.findData(_er_id)
            if idx >= 0:
                self.elevation_raster_combo.setCurrentIndex(idx)

        for fld in ("info_title", "info_client", "info_client_img",
                    "info_project_number", "info_project", "info_project_img",
                    "info_doc_number", "info_revision", "info_created_by_name"):
            val = s.value(f"{_SETTINGS_KEY}/{fld}", "")
            if val:
                getattr(self, f"{fld}_edit").setText(val)

        text = s.value(f"{_SETTINGS_KEY}/info_text", "")
        if text:
            self._set_richtext(self.info_text_edit, text)

        purpose_val = s.value(f"{_SETTINGS_KEY}/info_purpose", "")
        if purpose_val:
            idx = self.info_purpose_combo.findText(purpose_val)
            if idx >= 0:
                self.info_purpose_combo.setCurrentIndex(idx)
            else:
                self.info_purpose_combo.setEditText(purpose_val)

        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                val = s.value(f"{_SETTINGS_KEY}/info_{role}_{part}", "")
                if val:
                    getattr(self, f"info_{role}_{part}_edit").setText(val)

        theme_val = s.value(f"{_SETTINGS_KEY}/export_theme", "corporate")
        idx = self.export_theme_combo.findData(theme_val)
        if idx >= 0:
            self.export_theme_combo.setCurrentIndex(idx)
        key = f"{_SETTINGS_KEY}/save_config_on_export"
        if s.contains(key):
            self.save_config_on_export_cb.setChecked(s.value(key, True, type=bool))
        import json as _json
        try:
            cl_raw = s.value(f"{_SETTINGS_KEY}/changelog", "[]")
            self._changelog = _json.loads(cl_raw) if cl_raw else []
        except Exception:
            self._changelog = []
        self._changelog_refresh_list()
        mode_val = s.value(f"{_SETTINGS_KEY}/mode", "pro")
        if mode_val not in ("lite", "pro", "3d"):
            mode_val = "lite" if s.value(f"{_SETTINGS_KEY}/lite_mode", False, type=bool) else "pro"
        self._set_mode(mode_val)

    def _save_settings(self):
        s = QSettings()
        s.setValue(f"{_SETTINGS_KEY}/include_layer_control", self.layer_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_basemap",       self.basemap_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_info",          self.include_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_project_info",  self.include_project_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_doc_metadata",  self.include_doc_metadata_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_doc_control",   self.include_doc_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/info_title",            self.info_title_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_text",             self.info_text_edit.toHtml())
        for fld in ("info_client", "info_client_img",
                    "info_project_number", "info_project", "info_project_img",
                    "info_doc_number", "info_revision", "info_created_by_name"):
            s.setValue(f"{_SETTINGS_KEY}/{fld}", getattr(self, f"{fld}_edit").text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_purpose", self.info_purpose_combo.currentText().strip())
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                s.setValue(f"{_SETTINGS_KEY}/info_{role}_{part}",
                           getattr(self, f"info_{role}_{part}_edit").text().strip())
        s.setValue(f"{_SETTINGS_KEY}/export_theme", self.export_theme_combo.currentData())
        s.setValue(f"{_SETTINGS_KEY}/save_config_on_export", self.save_config_on_export_cb.isChecked())
        for flag, attr in (
            ("feat_identify",         "feat_identify_cb"),
            ("feat_attr_table",       "feat_attr_table_cb"),
            ("feat_attr_csv",         "feat_attr_csv_cb"),
            ("feat_attr_geojson",     "feat_attr_geojson_cb"),
            ("feat_measure",          "feat_measure_cb"),
            ("feat_filter",           "feat_filter_cb"),
            ("feat_search",           "feat_search_cb"),
            ("feat_minimap",          "feat_minimap_cb"),
            ("feat_fancy_labels",     "feat_fancy_labels_cb"),
            ("feat_changelog",        "feat_changelog_cb"),
            ("feat_3d",               "feat_3d_cb"),
            ("feat_sketch",           "feat_sketch_cb"),
        ):
            s.setValue(f"{_SETTINGS_KEY}/{flag}", getattr(self, attr).isChecked())
        s.setValue(f"{_SETTINGS_KEY}/cesium_ion_token", self.cesium_ion_token_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/google_maps_key",  self.google_maps_key_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/extrude_field",       self.extrude_field_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/extrude_scale",       self.extrude_scale_spin.value())
        s.setValue(f"{_SETTINGS_KEY}/elevation_raster_id", self.elevation_raster_combo.currentData() or "")
        s.setValue(f"{_SETTINGS_KEY}/report_md_path",      self.report_md_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/report_figures_dir",  self.report_figures_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/cog_proxy",           self.cog_proxy_edit.text().strip())
        import json as _json
        s.setValue(f"{_SETTINGS_KEY}/changelog", _json.dumps(self._changelog))
        mode = "lite" if self._is_lite else ("3d" if self.feat_3d_cb.isChecked() else "pro")
        s.setValue(f"{_SETTINGS_KEY}/mode", mode)

    def _build_header(self):
        header = QWidget()
        header.setObjectName("icHeader")
        outer = QVBoxLayout(header)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Purple top strip: icon + InterMap title ───────────────────────────
        top = QWidget()
        top.setObjectName("icTop")
        top_vl = QVBoxLayout(top)
        top_vl.setContentsMargins(10, 10, 10, 10)
        top_vl.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        icon_lbl = QLabel()
        svg_icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(svg_icon_path):
            try:
                from qgis.PyQt.QtSvg import QSvgRenderer
                from qgis.PyQt.QtGui import QPainter
                renderer = QSvgRenderer(svg_icon_path)
                sz = 26
                pm = QPixmap(sz, sz)
                pm.fill(Qt.transparent)
                painter = QPainter(pm)
                renderer.render(painter)
                painter.end()
                icon_lbl.setPixmap(pm)
            except Exception:
                pass
        title_row.addWidget(icon_lbl)

        name_lbl = QLabel("InterMap")
        name_lbl.setObjectName("icName")
        title_row.addWidget(name_lbl)
        title_row.addStretch()
        toggle_frame = QFrame()
        toggle_frame.setObjectName("icModeToggle")
        toggle_frame.setStyleSheet(
            "#icModeToggle { background: rgba(255,255,255,0.12); "
            "border: 1px solid rgba(255,255,255,0.35); border-radius: 11px; padding: 1px; }"
        )
        toggle_layout = QHBoxLayout(toggle_frame)
        toggle_layout.setContentsMargins(2, 1, 2, 1)
        toggle_layout.setSpacing(0)

        _btn_base = (
            "QPushButton { background: transparent; color: rgba(255,255,255,0.65); "
            "border: none; border-radius: 9px; font-size: 10px; font-weight: 600; padding: 2px 9px; } "
            "QPushButton:hover { color: rgba(255,255,255,0.9); }"
        )
        _btn_active = (
            f"QPushButton {{ background: rgba(255,255,255,0.9); color: {_PURPLE}; "
            "border: none; border-radius: 9px; font-size: 10px; font-weight: 700; padding: 2px 9px; }"
        )
        _btn_disabled = (
            "QPushButton { background: transparent; color: rgba(255,255,255,0.22); "
            "border: none; border-radius: 9px; font-size: 10px; font-weight: 600; padding: 2px 9px; }"
        )

        self._btn_lite = QPushButton("Lite")
        self._btn_lite.setObjectName("icModeLite")
        self._btn_lite.setToolTip("Lite mode — simplified single-layer map")
        self._btn_lite.setStyleSheet(_btn_base)
        self._btn_lite.clicked.connect(lambda: self._set_mode("lite"))

        self._btn_pro = QPushButton("Pro")
        self._btn_pro.setObjectName("icModePro")
        self._btn_pro.setToolTip("Pro mode — full project with info tab, views and metadata")
        self._btn_pro.setStyleSheet(_btn_active)  # default active
        self._btn_pro.clicked.connect(lambda: self._set_mode("pro"))

        self._btn_3d = QPushButton("3D")
        self._btn_3d.setObjectName("icMode3D")
        self._btn_3d.setToolTip(
            "3D mode — Pro export with Cesium.js 3D view enabled.\n"
            "Requires a Cesium Ion token and an internet connection."
        )
        self._btn_3d.setStyleSheet(_btn_base)
        self._btn_3d.clicked.connect(lambda: self._set_mode("3d"))

        self._toggle_btn_styles = (_btn_base, _btn_active, _btn_disabled)

        toggle_layout.addWidget(self._btn_lite)
        toggle_layout.addWidget(self._btn_pro)
        toggle_layout.addWidget(self._btn_3d)
        title_row.addWidget(toggle_frame)
        top_vl.addLayout(title_row)
        outer.addWidget(top)

        # ── White strip: descriptions only (no company logo) ───────────────────────
        desc_strip = QWidget()
        desc_strip.setObjectName("icLogoStrip")
        desc_vl = QVBoxLayout(desc_strip)
        desc_vl.setContentsMargins(10, 6, 10, 6)
        desc_vl.setSpacing(3)

        desc1 = QLabel(
            "Plugin to generate interactive map packages in a standalone shareable HTML file."
        )
        desc1.setObjectName("icDesc1")
        desc1.setWordWrap(True)
        desc_vl.addWidget(desc1)
        self._header_desc1 = desc1

        desc2 = QLabel(
            "This plugin is in open beta — for feature requests, bugs or further info "
            "reach out to Luke Johnstone."
        )
        desc2.setObjectName("icDesc2")
        desc2.setWordWrap(True)
        desc_vl.addWidget(desc2)

        outer.addWidget(desc_strip)

        return header

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        container.setStyleSheet(f"""
            QWidget#icTop {{
                background: {_PURPLE};
                border-bottom: 3px solid {_PURPLE_DARK};
            }}
            QWidget#icLogoStrip {{
                background: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }}
            QWidget#icConfigBar {{
                background: #F8F9FB;
                border-bottom: 1px solid #E2E8F0;
            }}
            QLabel#icConfigName {{
                color: #374151;
                font-size: 11px;
            }}
            QPushButton#icConfigSave {{
                background: {_PURPLE};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 11px;
            }}
            QPushButton#icConfigSave:hover {{ background: {_PURPLE_DARK}; }}
            QPushButton#icConfigSaveRed {{
                background: #DC2626;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 11px;
            }}
            QPushButton#icConfigSaveRed:hover {{ background: #B91C1C; }}
            QLabel#icName {{
                color: #FFFFFF;
                font-size: 22px;
                font-weight: 700;
            }}
            QLabel#icDesc1 {{
                color: #475569;
            }}
            QLabel#icDesc2 {{
                color: #DC2626;
            }}
            QWidget#icNavBar {{
                background: #FFFFFF;
                border-bottom: 2px solid {_PURPLE};
            }}
            QPushButton#icNavBtn {{
                background: transparent;
                border: none;
                padding: 6px 14px;
                color: #6B7280;
                font-size: 11px;
                font-weight: 600;
                min-width: 64px;
            }}
            QPushButton#icNavBtn:checked {{
                color: {_PURPLE};
                border-bottom: 3px solid {_PURPLE};
            }}
            QPushButton#icNavBtn:hover:!checked {{
                color: {_PURPLE_LIGHT};
            }}
            QLabel#icNavSep {{
                color: #D1D5DB;
                font-size: 13px;
                padding: 0 2px;
            }}
            QGroupBox {{
                border: 1px solid #E2E8F0;
                border-radius: 5px;
                margin-top: 16px;
                padding-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                top: -1px;
                left: 8px;
                padding: 0 4px;
                color: #374151;
                font-weight: 600;
                font-size: 10px;
            }}
            QGroupBox#greyBox {{
                background: #F8F9FB;
                border: 1px solid #D1D5DB;
            }}
            QPushButton#exportBtn {{
                background: {_PURPLE};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 22px;
                font-weight: 600;
                min-height: 26px;
            }}
            QPushButton#exportBtn:hover   {{ background: {_PURPLE_DARK}; }}
            QPushButton#exportBtn:pressed {{ background: {_PURPLE_DARK}; }}
            QPushButton#deleteBtn {{
                background: #DC2626;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: 600;
                min-height: 26px;
            }}
            QPushButton#deleteBtn:hover   {{ background: #B91C1C; }}
            QPushButton#deleteBtn:pressed {{ background: #991B1B; }}
            QPushButton#icModeBtn {{
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.35);
                color: rgba(255,255,255,0.9);
                border-radius: 10px;
                font-size: 10px;
                font-weight: 600;
                padding: 2px 9px;
                letter-spacing: 0.04em;
            }}
            QPushButton#icModeBtn:hover {{
                background: rgba(255,255,255,0.28);
            }}
            QPushButton#icNavBtn:disabled {{
                color: #C0C0C0;
                text-decoration: line-through;
            }}
        """)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_config_bar())

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 6, 8, 0)
        inner_layout.setSpacing(4)

        # ── Step navigation bar (replaces QTabWidget) ─────────────────────
        nav_bar = QWidget()
        nav_bar.setObjectName("icNavBar")
        nav_hl = QHBoxLayout(nav_bar)
        nav_hl.setContentsMargins(6, 0, 6, 0)
        nav_hl.setSpacing(0)

        self._tab_stack = QStackedWidget()
        self._nav_btns = []
        self._nav_seps = []

        _tab_defs = [
            ("Map Info",     self._build_map_info_tab()),
            ("Map Views",    self._build_map_views_tab()),
            ("Layers",       self._build_layers_tab()),
            ("Export",       self._build_export_tab()),
            ("Layers Lite",  self._build_lite_layers_tab()),
        ]
        for i, (label, page_widget) in enumerate(_tab_defs):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("icNavSep")
                nav_hl.addWidget(sep)
                self._nav_seps.append(sep)
            btn = QPushButton(label)
            btn.setObjectName("icNavBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked, idx=i: self._switch_tab(idx))
            self._nav_btns.append(btn)
            nav_hl.addWidget(btn)
            self._tab_stack.addWidget(page_widget)

        nav_hl.addStretch()
        # Hide Lite button and its separator initially (Pro mode default)
        self._nav_btns[4].setVisible(False)
        self._nav_seps[3].setVisible(False)
        inner_layout.addWidget(nav_bar)

        # _content_stack: page 0 = tabs, page 1 = expanded rich-text editor
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._tab_stack)
        self._content_stack.addWidget(self._build_rt_expand_widget())
        inner_layout.addWidget(self._content_stack, 1)
        self._switch_tab(0)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        inner_layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("exportBtn")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._on_close_clicked)
        bottom.addStretch()
        bottom.addWidget(self.export_btn)
        bottom.addWidget(close_btn)
        inner_layout.addLayout(bottom)

        layout.addWidget(inner)
        self.setWidget(container)

        self.info_project_number_edit.textChanged.connect(self._update_config_bar)
        self.include_project_info_cb.toggled.connect(self._update_config_bar)

        for _sig in [
            self.info_title_edit.textChanged,
            self.info_text_edit.textChanged,
            self.export_theme_combo.currentIndexChanged,
            self.include_info_cb.toggled,
            self.include_doc_metadata_cb.toggled,
            self.include_project_info_cb.toggled,
            self.include_doc_control_cb.toggled,
            self.layer_control_cb.toggled,
            self.basemap_cb.toggled,
        ]:
            _sig.connect(self._mark_unsaved)

    def _switch_tab(self, idx):
        prev = self._tab_stack.currentIndex()
        self._tab_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == idx)
        if prev == self._MAP_VIEWS_TAB and idx != self._MAP_VIEWS_TAB:
            self._mv_clear_rubber_bands()
        elif idx == self._MAP_VIEWS_TAB and prev != self._MAP_VIEWS_TAB:
            self._mv_update_rubber_bands()

    def _set_mode(self, mode: str):
        """mode is one of 'lite', 'pro', '3d'."""
        self._is_lite = (mode == "lite")
        _btn_base, _btn_active, _ = self._toggle_btn_styles
        self._btn_lite.setStyleSheet(_btn_active if mode == "lite" else _btn_base)
        self._btn_pro.setStyleSheet(_btn_active  if mode == "pro"  else _btn_base)
        self._btn_3d.setStyleSheet(_btn_active   if mode == "3d"   else _btn_base)

        if mode == "lite":
            self._header_desc1.setText(
                "Lite: creates a simplified interactive web map with no project "
                "information tab and a single set of layers."
            )
        elif mode == "3d":
            self._header_desc1.setText(
                "3D: Pro export with Cesium.js 3D view enabled. "
                "Requires a Cesium Ion token and an internet connection at viewing time."
            )
        else:
            self._header_desc1.setText(
                "Pro: creates interactive map packages with a project information tab, "
                "multiple preset views and document control metadata."
            )

        is_lite = (mode == "lite")
        for i in range(3):
            self._nav_btns[i].setEnabled(not is_lite)
        self._nav_btns[self._LITE_TAB].setVisible(is_lite)
        self._nav_seps[self._LITE_TAB - 1].setVisible(is_lite)
        if is_lite:
            self._lite_populate_layers()
            self._switch_tab(self._LITE_TAB)
        else:
            self._switch_tab(0)

        # Automatically check/uncheck the 3D feature toggle
        try:
            self.feat_3d_cb.setChecked(mode == "3d")
            self.d3_group.setEnabled(mode == "3d")
        except AttributeError:
            pass

    def _update_initial_extent_label(self):
        pass  # label removed; _initial_extent still used in export

    def _save_to_downloads(self):
        self.path_edit.setText(self._default_output_path())
