import os
import json
import datetime
from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QFileDialog, QLineEdit,
    QMessageBox, QProgressBar, QCheckBox, QGroupBox,
    QTabWidget, QTextEdit, QFormLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QComboBox, QInputDialog,
    QScrollArea, QMenu, QGridLayout, QAbstractItemView, QSizePolicy,
    QStackedWidget,
)
from qgis.PyQt.QtCore import Qt, QStandardPaths, QUrl, QSettings, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QPixmap, QColor
from qgis.core import (
    QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer,
    QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsRectangle, QgsPointXY, QgsWkbTypes,
)

_SETTINGS_KEY = "QgsWebMapExporter"
_INSTANCES_KEY = f"{_SETTINGS_KEY}/instances"

_PURPOSE_OPTIONS = [
    "",
    "P1 – Preliminary",
    "P2 – Work in Progress",
    "P3 – Suitable for Coordination",
    "P4 – Suitable for Review",
    "P5 – Suitable for Information",
    "P6 – Suitable for Construction",
    "P7 – As Built / Record",
]

_AR_PURPLE       = "#3f32f1"
_AR_PURPLE_DARK  = "#2b22c0"
_AR_PURPLE_LIGHT = "#7066f5"


# ── Drag-to-draw extent tool ──────────────────────────────────────────────────

class _RectExtentTool:
    """Minimal wrapper that activates a rubber-band rectangle drawing tool on the
    QGIS map canvas. Calls ``callback(QgsRectangle)`` in canvas CRS on release."""

    def __init__(self, canvas, callback):
        try:
            from qgis.gui import QgsMapTool, QgsRubberBand
            from qgis.PyQt.QtCore import pyqtSignal

            class _Tool(QgsMapTool):
                rectDrawn = pyqtSignal(object)

                def __init__(self, cv):
                    super().__init__(cv)
                    self._rb = QgsRubberBand(cv, QgsWkbTypes.PolygonGeometry)
                    self._rb.setStrokeColor(QColor(_AR_PURPLE))
                    self._rb.setFillColor(QColor(63, 50, 241, 25))
                    self._rb.setWidth(2)
                    self._start = None

                def canvasPressEvent(self, e):
                    self._start = self.toMapCoordinates(e.pos())
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)

                def canvasMoveEvent(self, e):
                    if not self._start:
                        return
                    end = self.toMapCoordinates(e.pos())
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    for pt in [
                        QgsPointXY(self._start.x(), self._start.y()),
                        QgsPointXY(self._start.x(), end.y()),
                        QgsPointXY(end.x(), end.y()),
                        QgsPointXY(end.x(), self._start.y()),
                        QgsPointXY(self._start.x(), self._start.y()),
                    ]:
                        self._rb.addPoint(pt)

                def canvasReleaseEvent(self, e):
                    if not self._start:
                        return
                    end = self.toMapCoordinates(e.pos())
                    rect = QgsRectangle(self._start, end)
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    self._start = None
                    if not rect.isEmpty():
                        self.rectDrawn.emit(rect)

                def deactivate(self):
                    self._rb.reset(QgsWkbTypes.PolygonGeometry)
                    super().deactivate()

            self._tool = _Tool(canvas)
            self._tool.rectDrawn.connect(callback)
            self._prev = canvas.mapTool()
            canvas.setMapTool(self._tool)
            self._canvas = canvas
        except Exception:
            self._tool = None

    def deactivate(self):
        if self._tool and self._canvas:
            try:
                self._canvas.setMapTool(self._prev)
            except Exception:
                pass


# ── Main dialog ───────────────────────────────────────────────────────────────

class WebMapExportDialog(QDockWidget):
    """Dockable InterCarta export panel."""

    def __init__(self, iface, parent=None):
        super().__init__("InterCarta", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("InterCartaPanel")
        self.setMinimumWidth(420)
        self._initial_extent = self._capture_canvas_extent()
        self._map_views = []
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

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._mv_clear_rubber_bands()
        self._save_settings()
        super().closeEvent(event)

    def _on_close_clicked(self):
        self._mv_clear_rubber_bands()
        self._save_settings()
        self.hide()

    # ── Canvas / path helpers ─────────────────────────────────────────────────

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

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self):
        s = QSettings()
        for flag, attr in (
            ("include_layer_control", "layer_control_cb"),
            ("include_basemap",       "basemap_cb"),
            ("include_info",          "include_info_cb"),
            ("include_project_info",  "include_project_info_cb"),
            ("include_doc_metadata",  "include_doc_metadata_cb"),
            ("include_doc_control",   "include_doc_control_cb"),
        ):
            key = f"{_SETTINGS_KEY}/{flag}"
            if s.contains(key):
                getattr(self, attr).setChecked(s.value(key, True, type=bool))

        for fld in ("info_title", "info_client", "info_client_img",
                    "info_project_number", "info_project", "info_project_img",
                    "info_doc_number", "info_revision", "info_created_by_name"):
            val = s.value(f"{_SETTINGS_KEY}/{fld}", "")
            if val:
                getattr(self, f"{fld}_edit").setText(val)

        text = s.value(f"{_SETTINGS_KEY}/info_text", "")
        if text:
            self.info_text_edit.setPlainText(text)

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

    def _save_settings(self):
        s = QSettings()
        s.setValue(f"{_SETTINGS_KEY}/include_layer_control", self.layer_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_basemap",       self.basemap_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_info",          self.include_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_project_info",  self.include_project_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_doc_metadata",  self.include_doc_metadata_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_doc_control",   self.include_doc_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/info_title",            self.info_title_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_text",             self.info_text_edit.toPlainText().strip())
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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_header(self):
        header = QWidget()
        header.setObjectName("icHeader")
        outer = QVBoxLayout(header)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Purple top strip: icon + InterCarta title only ────────────────────
        top = QWidget()
        top.setObjectName("icTop")
        top_vl = QVBoxLayout(top)
        top_vl.setContentsMargins(10, 10, 10, 10)
        top_vl.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            icon_lbl = QLabel()
            pm = QPixmap(icon_path).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pm)
            title_row.addWidget(icon_lbl)
        name_lbl = QLabel("InterCarta")
        name_lbl.setObjectName("icName")
        title_row.addWidget(name_lbl)
        title_row.addStretch()
        top_vl.addLayout(title_row)
        outer.addWidget(top)

        # ── White logo strip: AtkinsRéalis wordmark + descriptions ───────────
        logo_strip = QWidget()
        logo_strip.setObjectName("icLogoStrip")
        logo_vl = QVBoxLayout(logo_strip)
        logo_vl.setContentsMargins(10, 6, 10, 6)
        logo_vl.setSpacing(4)

        svg_path = os.path.join(os.path.dirname(__file__), "vendor", "Logo.svg")
        if os.path.exists(svg_path):
            try:
                from qgis.PyQt.QtSvg import QSvgRenderer
                from qgis.PyQt.QtGui import QPainter
                renderer = QSvgRenderer(svg_path)
                logo_h = 20
                logo_w = int(logo_h * (354.3684 / 47.7976))
                pm = QPixmap(logo_w, logo_h)
                pm.fill(Qt.transparent)
                painter = QPainter(pm)
                renderer.render(painter)
                painter.end()
                logo_lbl = QLabel()
                logo_lbl.setPixmap(pm)
                logo_vl.addWidget(logo_lbl)
            except Exception:
                logo_vl.addWidget(QLabel("AtkinsRéalis"))
        else:
            logo_vl.addWidget(QLabel("AtkinsRéalis"))

        desc1 = QLabel(
            "Plugin to generate interactive map packages in a standalone shareable HTML file."
        )
        desc1.setObjectName("icDesc1")
        desc1.setWordWrap(True)
        logo_vl.addWidget(desc1)

        desc2 = QLabel(
            "This plugin is in open beta — for feature requests, bugs or further info "
            "reach out to Luke.Johnstone@Atkinsrealis.com"
        )
        desc2.setObjectName("icDesc2")
        desc2.setWordWrap(True)
        logo_vl.addWidget(desc2)

        outer.addWidget(logo_strip)

        return header

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        container.setStyleSheet(f"""
            QWidget#icTop {{
                background: {_AR_PURPLE};
                border-bottom: 3px solid {_AR_PURPLE_DARK};
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
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton#icConfigSave {{
                background: {_AR_PURPLE};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 11px;
            }}
            QPushButton#icConfigSave:hover {{ background: {_AR_PURPLE_DARK}; }}
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
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#icDesc1 {{
                color: #475569;
                font-size: 10px;
            }}
            QLabel#icDesc2 {{
                color: #DC2626;
                font-size: 10px;
            }}
            QWidget#icNavBar {{
                background: #FFFFFF;
                border-bottom: 2px solid {_AR_PURPLE};
            }}
            QPushButton#icNavBtn {{
                background: transparent;
                border: none;
                padding: 6px 10px;
                color: #6B7280;
                font-size: 11px;
            }}
            QPushButton#icNavBtn:checked {{
                color: {_AR_PURPLE};
                font-weight: 700;
                border-bottom: 2px solid {_AR_PURPLE};
            }}
            QPushButton#icNavBtn:hover:!checked {{
                color: {_AR_PURPLE_LIGHT};
            }}
            QLabel#icNavSep {{
                color: #D1D5DB;
                font-size: 13px;
                padding: 0 2px;
            }}
            QGroupBox {{
                border: 1px solid #E2E8F0;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                color: {_AR_PURPLE};
                font-weight: 600;
            }}
            QGroupBox#greyBox {{
                background: #F8F9FB;
                border: 1px solid #D1D5DB;
            }}
            QPushButton#exportBtn {{
                background: {_AR_PURPLE};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 22px;
                font-weight: 600;
                min-height: 26px;
            }}
            QPushButton#exportBtn:hover   {{ background: {_AR_PURPLE_DARK}; }}
            QPushButton#exportBtn:pressed {{ background: {_AR_PURPLE_DARK}; }}
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

        _tab_defs = [
            ("Map Info",  self._build_map_info_tab()),
            ("Map Views", self._build_map_views_tab()),
            ("Layers",    self._build_layers_tab()),
            ("Export",    self._build_export_tab()),
        ]
        for i, (label, page_widget) in enumerate(_tab_defs):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("icNavSep")
                nav_hl.addWidget(sep)
            btn = QPushButton(label)
            btn.setObjectName("icNavBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked, idx=i: self._switch_tab(idx))
            self._nav_btns.append(btn)
            nav_hl.addWidget(btn)
            self._tab_stack.addWidget(page_widget)

        nav_hl.addStretch()
        inner_layout.addWidget(nav_bar)
        inner_layout.addWidget(self._tab_stack, 1)
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

    _MAP_VIEWS_TAB = 1

    def _switch_tab(self, idx):
        prev = self._tab_stack.currentIndex()
        self._tab_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == idx)
        if prev == self._MAP_VIEWS_TAB and idx != self._MAP_VIEWS_TAB:
            self._mv_clear_rubber_bands()
        elif idx == self._MAP_VIEWS_TAB and prev != self._MAP_VIEWS_TAB:
            self._mv_update_rubber_bands()

    # ── Config bar ────────────────────────────────────────────────────────────

    def _build_config_bar(self):
        bar = QWidget()
        bar.setObjectName("icConfigBar")
        bar_hl = QHBoxLayout(bar)
        bar_hl.setContentsMargins(8, 5, 8, 5)
        bar_hl.setSpacing(6)

        # State: no config loaded
        self._config_none_widget = QWidget()
        none_hl = QHBoxLayout(self._config_none_widget)
        none_hl.setContentsMargins(0, 0, 0, 0)
        none_hl.setSpacing(6)
        load_btn = QPushButton("Load Config")
        load_btn.clicked.connect(self._config_bar_load)
        none_hl.addWidget(load_btn)
        create_btn = QPushButton("Create Config")
        create_btn.clicked.connect(self._config_bar_create)
        none_hl.addWidget(create_btn)
        none_hl.addStretch()
        bar_hl.addWidget(self._config_none_widget)

        # State: config loaded
        self._config_loaded_widget = QWidget()
        loaded_hl = QHBoxLayout(self._config_loaded_widget)
        loaded_hl.setContentsMargins(0, 0, 0, 0)
        loaded_hl.setSpacing(6)
        self.config_name_label = QLabel("")
        self.config_name_label.setObjectName("icConfigName")
        loaded_hl.addWidget(self.config_name_label)
        loaded_hl.addStretch()
        self.config_save_btn = QPushButton("Save")
        self.config_save_btn.setObjectName("icConfigSave")
        self.config_save_btn.clicked.connect(self._instance_save)
        loaded_hl.addWidget(self.config_save_btn)
        self.config_menu_btn = QPushButton("☰")
        self.config_menu_btn.setFixedWidth(32)
        self.config_menu_btn.setToolTip("Switch / Load, Save As, Delete")
        self.config_menu_btn.clicked.connect(self._show_config_menu)
        loaded_hl.addWidget(self.config_menu_btn)
        bar_hl.addWidget(self._config_loaded_widget)

        self._update_config_bar()
        return bar

    def _update_config_bar(self):
        loaded = self._loaded_instance_name is not None
        self._config_none_widget.setVisible(not loaded)
        self._config_loaded_widget.setVisible(loaded)
        if loaded:
            self.config_name_label.setText(f"Config: {self._loaded_instance_name}")
            self._refresh_config_save_btn()

    def _refresh_config_save_btn(self):
        obj = "icConfigSaveRed" if self._has_unsaved_changes else "icConfigSave"
        self.config_save_btn.setObjectName(obj)
        self.config_save_btn.style().unpolish(self.config_save_btn)
        self.config_save_btn.style().polish(self.config_save_btn)

    def _mark_unsaved(self, *_):
        if self._loaded_instance_name is None:
            return
        self._has_unsaved_changes = True
        self._refresh_config_save_btn()

    def _config_bar_load(self):
        data = self._instances_load_all()
        if not data:
            QMessageBox.information(self, "No saved configs",
                "No saved configurations found. Use 'Create Config' to save the current settings.")
            return
        names = sorted(data.keys(), key=str.lower)
        name, ok = QInputDialog.getItem(self, "Load Config", "Select a saved config:", names, 0, False)
        if not ok or not name:
            return
        state = data.get(name)
        if state is None:
            return
        self._apply_state(state)
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        self._update_config_bar()
        missing = self._missing_layer_names(state.get("layer_names", []))
        if missing:
            QMessageBox.information(
                self, "Loaded with missing layers",
                "Config '{}' loaded.\n\nLayers not in current project (skipped):\n  • {}".format(
                    name, "\n  • ".join(missing))
            )

    def _config_bar_create(self):
        name, ok = QInputDialog.getText(self, "Create Config", "New config name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Please enter a name.")
            return
        data = self._instances_load_all()
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        self._update_config_bar()
        self.iface.messageBar().pushInfo("InterCarta", f"Config '{name}' created.")

    def _show_config_menu(self):
        menu = QMenu(self)
        switch_act  = menu.addAction("Switch / Load…")
        save_as_act = menu.addAction("Save As…")
        menu.addSeparator()
        del_act = menu.addAction("Delete")
        btn = self.sender()
        action = menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action == switch_act:
            self._config_bar_load()
        elif action == save_as_act:
            self._instance_save_as()
        elif action == del_act:
            self._instance_delete()

    # ── Map Info tab ──────────────────────────────────────────────────────────

    def _build_map_info_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 8)
        layout.setSpacing(6)

        # ── Map info (grey box) ───────────────────────────────────────────────
        self.include_info_cb = QCheckBox("Include 'About this map' info panel")
        self.include_info_cb.setChecked(True)
        layout.addWidget(self.include_info_cb)

        info_group = QGroupBox("Map info")
        info_group.setObjectName("greyBox")
        info_form = QFormLayout(info_group)
        info_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.info_title_edit = QLineEdit()
        self.info_title_edit.setText(QgsProject.instance().baseName() or "")
        self.info_title_edit.setPlaceholderText("Panel title…")
        info_form.addRow("Title:", self.info_title_edit)
        self.info_text_edit = QTextEdit()
        self.info_text_edit.setPlaceholderText("Description / information text…")
        self.info_text_edit.setMinimumHeight(80)
        info_form.addRow("Description:", self.info_text_edit)
        layout.addWidget(info_group)

        # ── Document metadata (optional grey box) ────────────────────────────
        self.include_doc_metadata_cb = QCheckBox("Include document metadata")
        self.include_doc_metadata_cb.setChecked(True)
        layout.addWidget(self.include_doc_metadata_cb)

        self.doc_meta_widget = QGroupBox("Document metadata")
        self.doc_meta_widget.setObjectName("greyBox")
        dm_form = QFormLayout(self.doc_meta_widget)
        dm_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.info_doc_number_edit = QLineEdit()
        self.info_doc_number_edit.setPlaceholderText("Document number…")
        dm_form.addRow("Doc number:", self.info_doc_number_edit)
        self.info_revision_edit = QLineEdit()
        self.info_revision_edit.setPlaceholderText("e.g. P1.02…")
        dm_form.addRow("Revision:", self.info_revision_edit)
        self.info_purpose_combo = QComboBox()
        self.info_purpose_combo.setEditable(True)
        for opt in _PURPOSE_OPTIONS:
            self.info_purpose_combo.addItem(opt)
        dm_form.addRow("Purpose of issue:", self.info_purpose_combo)
        layout.addWidget(self.doc_meta_widget)
        self.include_doc_metadata_cb.toggled.connect(self.doc_meta_widget.setVisible)

        # ── Project information (optional grey box) ───────────────────────────
        self.include_project_info_cb = QCheckBox("Include project information")
        self.include_project_info_cb.setChecked(True)
        layout.addWidget(self.include_project_info_cb)

        self.proj_info_widget = QGroupBox("Project information")
        self.proj_info_widget.setObjectName("greyBox")
        proj_form = QFormLayout(self.proj_info_widget)
        proj_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.info_client_edit = QLineEdit()
        self.info_client_edit.setPlaceholderText("Client name…")
        proj_form.addRow("Client:", self.info_client_edit)

        _cimg_w = QWidget()
        _cimg_l = QHBoxLayout(_cimg_w)
        _cimg_l.setContentsMargins(0, 0, 0, 0)
        self.info_client_img_edit = QLineEdit()
        self.info_client_img_edit.setPlaceholderText("Client image path (optional)…")
        _cimg_btn = QPushButton("…")
        _cimg_btn.setFixedWidth(32)
        _cimg_btn.clicked.connect(lambda: self._browse_image(self.info_client_img_edit))
        _cimg_l.addWidget(self.info_client_img_edit)
        _cimg_l.addWidget(_cimg_btn)
        proj_form.addRow("Client image:", _cimg_w)

        self.info_project_number_edit = QLineEdit()
        self.info_project_number_edit.setPlaceholderText("Project number…")
        proj_form.addRow("Project number:", self.info_project_number_edit)

        self.info_project_edit = QLineEdit()
        self.info_project_edit.setPlaceholderText("Project name…")
        proj_form.addRow("Project name:", self.info_project_edit)

        _pimg_w = QWidget()
        _pimg_l = QHBoxLayout(_pimg_w)
        _pimg_l.setContentsMargins(0, 0, 0, 0)
        self.info_project_img_edit = QLineEdit()
        self.info_project_img_edit.setPlaceholderText("Project image path (optional)…")
        _pimg_btn = QPushButton("…")
        _pimg_btn.setFixedWidth(32)
        _pimg_btn.clicked.connect(lambda: self._browse_image(self.info_project_img_edit))
        _pimg_l.addWidget(self.info_project_img_edit)
        _pimg_l.addWidget(_pimg_btn)
        proj_form.addRow("Project image:", _pimg_w)

        layout.addWidget(self.proj_info_widget)
        self.include_project_info_cb.toggled.connect(self.proj_info_widget.setVisible)

        # ── Document control (optional grey box) ─────────────────────────────
        self.include_doc_control_cb = QCheckBox("Include document control")
        self.include_doc_control_cb.setChecked(True)
        layout.addWidget(self.include_doc_control_cb)

        self.doc_control_widget = QGroupBox("Document control")
        self.doc_control_widget.setObjectName("greyBox")
        dc_vl = QVBoxLayout(self.doc_control_widget)

        self.dc_grid_widget = QWidget()
        dc_grid = QGridLayout(self.dc_grid_widget)
        dc_grid.setContentsMargins(0, 0, 0, 0)
        dc_grid.addWidget(QLabel(""), 0, 0)
        dc_grid.addWidget(QLabel("<b>Name</b>"), 0, 1)
        dc_grid.addWidget(QLabel("<b>Date</b>"), 0, 2)
        for row_i, (label_text, key) in enumerate(
            [("Originated", "originated"), ("Checked", "checked"),
             ("Reviewed", "reviewed"), ("Approved", "approved")], start=1
        ):
            dc_grid.addWidget(QLabel(label_text + ":"), row_i, 0)
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("Name…")
            date_edit = QLineEdit()
            date_edit.setPlaceholderText("dd/mm/yyyy…")
            setattr(self, f"info_{key}_name_edit", name_edit)
            setattr(self, f"info_{key}_date_edit", date_edit)
            dc_grid.addWidget(name_edit, row_i, 1)
            dc_grid.addWidget(date_edit, row_i, 2)
        dc_grid.setColumnStretch(1, 2)
        dc_grid.setColumnStretch(2, 1)
        dc_vl.addWidget(self.dc_grid_widget)

        self.created_by_widget = QWidget()
        cb_hl = QHBoxLayout(self.created_by_widget)
        cb_hl.setContentsMargins(0, 0, 0, 0)
        cb_hl.addWidget(QLabel("Created by:"))
        self.info_created_by_name_edit = QLineEdit()
        self.info_created_by_name_edit.setPlaceholderText("Your name…")
        cb_hl.addWidget(self.info_created_by_name_edit, 1)
        cb_hl.addWidget(QLabel("on"))
        self._today_str = datetime.datetime.now().strftime("%d/%m/%Y")
        cb_hl.addWidget(QLabel(self._today_str))
        dc_vl.addWidget(self.created_by_widget)

        layout.addWidget(self.doc_control_widget)
        layout.addStretch()

        self.include_doc_control_cb.toggled.connect(self._on_doc_control_toggled)
        self._on_doc_control_toggled(True)

        scroll.setWidget(widget)
        return scroll

    def _on_doc_control_toggled(self, checked):
        self.dc_grid_widget.setVisible(checked)
        self.created_by_widget.setVisible(not checked)

    # ── Map Views tab ─────────────────────────────────────────────────────────

    def _build_map_views_tab(self):
        widget = QWidget()
        mv_layout = QVBoxLayout(widget)
        mv_layout.setContentsMargins(4, 4, 4, 4)
        mv_layout.setSpacing(4)

        # ── List ──────────────────────────────────────────────────────────────
        self.map_views_list_widget = QListWidget()
        self.map_views_list_widget.setFixedHeight(130)
        self.map_views_list_widget.setDragEnabled(True)
        self.map_views_list_widget.setAcceptDrops(True)
        self.map_views_list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.map_views_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.map_views_list_widget.currentRowChanged.connect(self._on_map_view_selected)
        self.map_views_list_widget.model().rowsMoved.connect(self._on_mv_rows_moved)
        mv_layout.addWidget(self.map_views_list_widget)

        # Add buttons (directly below list)
        add_row = QHBoxLayout()
        add_mv_btn = QPushButton("＋  Add map view")
        add_mv_btn.clicked.connect(self._map_view_add)
        add_row.addWidget(add_mv_btn)
        add_theme_btn = QPushButton("＋  Add from theme")
        add_theme_btn.setToolTip("Create a map view linked to a QGIS map theme")
        add_theme_btn.clicked.connect(self._map_view_add_from_theme)
        add_row.addWidget(add_theme_btn)
        mv_layout.addLayout(add_row)

        # ── Default detail (shown when Default item selected) ─────────────────
        self.mv_default_detail = QWidget()
        def_layout = QVBoxLayout(self.mv_default_detail)
        def_layout.setContentsMargins(0, 4, 0, 4)
        def_layout.setSpacing(6)
        def_lbl = QLabel("Default map state — applies before any map view is selected.")
        def_lbl.setStyleSheet("color: #6B7280; font-size: 10px; font-style: italic;")
        def_lbl.setWordWrap(True)
        def_layout.addWidget(def_lbl)
        def_ext_group = QGroupBox("Initial extent")
        def_ext_vl = QVBoxLayout(def_ext_group)
        def_ext_vl.setSpacing(4)
        set_init_btn = QPushButton("📷  Set from map canvas")
        set_init_btn.clicked.connect(self._recapture_initial_extent)
        def_ext_vl.addWidget(set_init_btn)
        self.default_extent_label = QLabel("(using full layer extent by default)")
        self.default_extent_label.setStyleSheet("color: #6B7280; font-size: 10px;")
        def_ext_vl.addWidget(self.default_extent_label)
        def_layout.addWidget(def_ext_group)
        def_layout.addStretch()
        mv_layout.addWidget(self.mv_default_detail, 1)
        self.mv_default_detail.setVisible(False)

        # ── Map view detail (shown when real view selected) ───────────────────
        self.mv_detail_scroll = QScrollArea()
        self.mv_detail_scroll.setWidgetResizable(True)
        self.mv_detail_scroll.setFrameShape(QScrollArea.NoFrame)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 4, 0, 4)
        detail_layout.setSpacing(6)

        view_canvas_btn = QPushButton("🗺  View in map canvas")
        view_canvas_btn.clicked.connect(self._mv_view_in_canvas)
        detail_layout.addWidget(view_canvas_btn)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.map_view_name_edit = QLineEdit()
        self.map_view_name_edit.setPlaceholderText("Map view name")
        self.map_view_name_edit.textChanged.connect(self._mv_autosave)
        name_row.addWidget(self.map_view_name_edit, 1)
        detail_layout.addLayout(name_row)

        detail_layout.addWidget(QLabel("Description:"))
        self.map_view_notes_edit = QTextEdit()
        self.map_view_notes_edit.setPlaceholderText("Description shown in the map viewer")
        self.map_view_notes_edit.setFixedHeight(56)
        self.map_view_notes_edit.textChanged.connect(self._mv_autosave)
        detail_layout.addWidget(self.map_view_notes_edit)

        # Visible layers
        layers_group = QGroupBox("Visible layers")
        layers_vl = QVBoxLayout(layers_group)
        layers_vl.setSpacing(4)
        copy_layers_btn = QPushButton("📷  Set to map canvas layers")
        copy_layers_btn.setToolTip("Snapshot which layers are currently visible in QGIS")
        copy_layers_btn.clicked.connect(self._map_view_capture_layers)
        layers_vl.addWidget(copy_layers_btn)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Slave to theme:"))
        self.import_theme_combo = QComboBox()
        self.import_theme_combo.setToolTip(
            "Link to a QGIS map theme — visibility is resolved dynamically at export time.\n"
            "Reload the plugin if a new theme does not appear here."
        )
        use_theme_btn = QPushButton("Link to theme")
        use_theme_btn.setToolTip("Store a dynamic reference to this theme (not a snapshot)")
        use_theme_btn.clicked.connect(self._map_view_use_theme)
        theme_row.addWidget(self.import_theme_combo, 1)
        theme_row.addWidget(use_theme_btn)
        layers_vl.addLayout(theme_row)
        self.map_view_layers_label = QLabel("Layers: (not set)")
        self.map_view_layers_label.setWordWrap(True)
        self.map_view_layers_label.setStyleSheet("color: #6B7280; font-size: 10px;")
        layers_vl.addWidget(self.map_view_layers_label)
        detail_layout.addWidget(layers_group)

        # View extent
        extent_group = QGroupBox("View extent")
        extent_vl = QVBoxLayout(extent_group)
        extent_vl.setSpacing(4)
        set_canvas_btn = QPushButton("📷  Set to map canvas extent")
        set_canvas_btn.clicked.connect(self._map_view_capture_extent)
        extent_vl.addWidget(set_canvas_btn)
        draw_btn = QPushButton("✏  Draw extent on map canvas")
        draw_btn.setToolTip("Click and drag a rectangle on the map canvas")
        draw_btn.clicked.connect(self._mv_start_draw_extent)
        extent_vl.addWidget(draw_btn)
        layer_ext_row = QHBoxLayout()
        layer_ext_row.addWidget(QLabel("From layer:"))
        self.mv_layer_extent_combo = QComboBox()
        set_layer_ext_btn = QPushButton("Set")
        set_layer_ext_btn.clicked.connect(self._mv_set_from_layer_extent)
        layer_ext_row.addWidget(self.mv_layer_extent_combo, 1)
        layer_ext_row.addWidget(set_layer_ext_btn)
        extent_vl.addLayout(layer_ext_row)
        self.map_view_extent_label = QLabel("(not set)")
        self.map_view_extent_label.setWordWrap(True)
        self.map_view_extent_label.setStyleSheet("color: #6B7280; font-size: 10px;")
        extent_vl.addWidget(self.map_view_extent_label)
        detail_layout.addWidget(extent_group)

        detail_layout.addStretch()

        del_btn = QPushButton("Delete this map view")
        del_btn.setObjectName("deleteBtn")
        del_btn.clicked.connect(self._map_view_delete)
        detail_layout.addWidget(del_btn)

        self.mv_detail_scroll.setWidget(detail_widget)
        mv_layout.addWidget(self.mv_detail_scroll, 1)
        self.mv_detail_scroll.setVisible(False)

        self._map_views_list_refresh()
        self._mv_populate_layer_combo()

        return widget

    # ── Map View helpers ──────────────────────────────────────────────────────

    def _mv_populate_layer_combo(self):
        """Fill the 'set extent from layer' combo with all project layers."""
        self.mv_layer_extent_combo.clear()
        try:
            for layer in QgsProject.instance().mapLayers().values():
                self.mv_layer_extent_combo.addItem(layer.name(), layer.id())
        except Exception:
            pass

    def _on_mv_rows_moved(self, _parent, start, _end, _dest, dest_row):
        # Guard: Default item must stay at position 0
        for i in range(self.map_views_list_widget.count()):
            if self.map_views_list_widget.item(i).data(Qt.UserRole) == -1 and i != 0:
                self._map_views_list_refresh()
                return

        new_order = []
        for i in range(self.map_views_list_widget.count()):
            orig_idx = self.map_views_list_widget.item(i).data(Qt.UserRole)
            if orig_idx is not None and orig_idx != -1 and 0 <= orig_idx < len(self._map_views):
                new_order.append(self._map_views[orig_idx])
        if len(new_order) == len(self._map_views):
            self._map_views = new_order
        # Re-index UserRole (skip Default at position 0)
        j = 0
        for i in range(self.map_views_list_widget.count()):
            item = self.map_views_list_widget.item(i)
            if item.data(Qt.UserRole) != -1:
                item.setData(Qt.UserRole, j)
                j += 1
        self._mv_update_rubber_bands()
        self._update_required_layers()

    def _mv_view_in_canvas(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        ext = self._map_views[idx].get("extent")
        if not ext:
            QMessageBox.information(self, "No extent", "This map view has no extent set yet.")
            return
        try:
            transformed = self._wgs84_to_canvas_rect(ext)
            self.iface.mapCanvas().setExtent(transformed)
            self.iface.mapCanvas().refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _mv_start_draw_extent(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        self.iface.messageBar().pushInfo(
            "InterCarta", "Click and drag on the map canvas to draw the extent."
        )
        self._mv_draw_tool = _RectExtentTool(
            self.iface.mapCanvas(), self._on_canvas_extent_drawn
        )

    def _on_canvas_extent_drawn(self, rect):
        """Called by _RectExtentTool with a QgsRectangle in canvas CRS."""
        try:
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(rect)
            ext = [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
            idx = self._editing_map_view_idx
            if idx is not None and 0 <= idx < len(self._map_views):
                self._map_views[idx]["extent"] = ext
                self._editing_map_view_extent = ext
                self._update_mv_extent_label(ext)
                self._mv_update_rubber_bands()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            if self._mv_draw_tool:
                self._mv_draw_tool.deactivate()
                self._mv_draw_tool = None

    def _mv_set_from_layer_extent(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        layer_id = self.mv_layer_extent_combo.currentData()
        if not layer_id:
            return
        try:
            layer = QgsProject.instance().mapLayer(layer_id)
            if not layer:
                return
            layer_crs = layer.crs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(layer_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(layer.extent())
            ext = [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
            self._map_views[idx]["extent"] = ext
            self._editing_map_view_extent = ext
            self._update_mv_extent_label(ext)
            self._mv_update_rubber_bands()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Map canvas rubber bands ───────────────────────────────────────────────

    def _mv_update_rubber_bands(self):
        self._mv_clear_rubber_bands()
        try:
            from qgis.gui import QgsRubberBand
        except ImportError:
            return

        canvas = self.iface.mapCanvas()
        selected_row = self.map_views_list_widget.currentRow()

        for i, mv in enumerate(self._map_views):
            ext = mv.get("extent")
            if not ext:
                continue
            try:
                transformed = self._wgs84_to_canvas_rect(ext)
                rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
                if i == selected_row:
                    rb.setStrokeColor(QColor(_AR_PURPLE))
                    rb.setWidth(2)
                    rb.setFillColor(QColor(63, 50, 241, 20))
                else:
                    rb.setStrokeColor(QColor(120, 120, 120, 180))
                    rb.setWidth(1)
                    rb.setFillColor(QColor(0, 0, 0, 0))
                xmin, ymin = transformed.xMinimum(), transformed.yMinimum()
                xmax, ymax = transformed.xMaximum(), transformed.yMaximum()
                for pt in [
                    QgsPointXY(xmin, ymin), QgsPointXY(xmin, ymax),
                    QgsPointXY(xmax, ymax), QgsPointXY(xmax, ymin),
                    QgsPointXY(xmin, ymin),
                ]:
                    rb.addPoint(pt)
                self._mv_rubber_bands[i] = rb
            except Exception:
                pass

    def _mv_clear_rubber_bands(self):
        for rb in self._mv_rubber_bands.values():
            try:
                rb.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                pass
        self._mv_rubber_bands = {}

    # ── Layers tab ────────────────────────────────────────────────────────────

    def _build_layers_tab(self):
        widget = QWidget()
        layers_layout = QVBoxLayout(widget)

        # Sub-header
        req_lbl = QLabel("Layers selected in map views are required and cannot be deselected.")
        req_lbl.setWordWrap(True)
        req_lbl.setStyleSheet(
            f"color: {_AR_PURPLE}; font-size: 10px; font-weight: 600; padding: 2px 0 4px 0;"
        )
        layers_layout.addWidget(req_lbl)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Apply QGIS theme:"))
        self.qgis_theme_combo = QComboBox()
        self.qgis_theme_combo.setToolTip(
            "Select a QGIS map theme to apply its layer visibility to the export list"
        )
        self.qgis_theme_combo.currentIndexChanged.connect(self._on_qgis_theme_combo_changed)
        theme_row.addWidget(self.qgis_theme_combo, 1)
        layers_layout.addLayout(theme_row)

        layer_group = QGroupBox("Layers to export")
        layer_layout = QVBoxLayout(layer_group)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        deselect_btn = QPushButton("Deselect All")
        deselect_btn.clicked.connect(self._deselect_all)
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(deselect_btn)
        btn_row.addStretch()
        layer_layout.addLayout(btn_row)

        self.layer_tree_widget = QTreeWidget()
        self.layer_tree_widget.setHeaderHidden(True)
        self.layer_tree_widget.setMinimumHeight(200)
        self.layer_tree_widget.itemChanged.connect(self._on_layer_item_changed)
        layer_layout.addWidget(self.layer_tree_widget)
        layers_layout.addWidget(layer_group)

        # Basemap option (directly under layer list)
        self.basemap_cb = QCheckBox("Add OpenStreetMap basemap")
        self.basemap_cb.setChecked(False)
        layers_layout.addWidget(self.basemap_cb)

        return widget

    # ── Export tab ────────────────────────────────────────────────────────────

    def _build_export_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        theme_group = QGroupBox("Theme")
        theme_form = QFormLayout(theme_group)
        self.export_theme_combo = QComboBox()
        self.export_theme_combo.addItem("Modern Corporate", "corporate")
        self.export_theme_combo.addItem("AtkinsRéalis Purple", "purple")
        self.export_theme_combo.addItem("Dark", "dark")
        self.export_theme_combo.setToolTip("Colour theme applied to the exported web map")
        theme_form.addRow("Theme:", self.export_theme_combo)
        layout.addWidget(theme_group)

        tools_group = QGroupBox("Tools")
        tools_layout = QVBoxLayout(tools_group)
        self.layer_control_cb = QCheckBox("Include legend / layer control (toggles + transparency)")
        self.layer_control_cb.setChecked(True)
        tools_layout.addWidget(self.layer_control_cb)
        layout.addWidget(tools_group)

        self.save_config_on_export_cb = QCheckBox("Save configuration on export")
        self.save_config_on_export_cb.setChecked(True)
        self.save_config_on_export_cb.setToolTip(
            "Automatically save the current settings to the active named config after each export"
        )
        layout.addWidget(self.save_config_on_export_cb)

        path_group = QGroupBox("Output file")
        path_vl = QVBoxLayout(path_group)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select output HTML file…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        path_vl.addLayout(path_row)
        downloads_btn = QPushButton("Save to downloads folder")
        downloads_btn.setToolTip("Reset to the default filename in your Downloads folder")
        downloads_btn.clicked.connect(self._save_to_downloads)
        path_vl.addWidget(downloads_btn)
        layout.addWidget(path_group)

        layout.addStretch()
        return widget

    # ── Instance manager ──────────────────────────────────────────────────────

    def _project_instances_key(self):
        path = QgsProject.instance().fileName()
        if not path:
            return f"{_SETTINGS_KEY}/instances/__no_project__"
        import hashlib
        h = hashlib.md5(path.encode("utf-8")).hexdigest()[:16]
        return f"{_SETTINGS_KEY}/project_instances/{h}"

    def _instances_load_all(self):
        key = self._project_instances_key()
        raw = QSettings().value(key, "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        old = QSettings().value(_INSTANCES_KEY, "")
        if old:
            try:
                data = json.loads(old)
                if isinstance(data, dict) and data:
                    return data
            except Exception:
                pass
        return {}

    def _instances_save_all(self, data):
        QSettings().setValue(self._project_instances_key(), json.dumps(data))

    def _instances_refresh_combo(self, select_name=None):
        # Legacy stub — config bar replaces the old combo
        self._update_config_bar()

    def _collect_state(self):
        info = {
            "enabled":             self.include_info_cb.isChecked(),
            "title":               self.info_title_edit.text().strip(),
            "text":                self.info_text_edit.toPlainText().strip(),
            "doc_number":          self.info_doc_number_edit.text().strip(),
            "revision":            self.info_revision_edit.text().strip(),
            "purpose":             self.info_purpose_combo.currentText().strip(),
            "client":              self.info_client_edit.text().strip(),
            "client_img":          self.info_client_img_edit.text().strip(),
            "project_number":      self.info_project_number_edit.text().strip(),
            "project":             self.info_project_edit.text().strip(),
            "project_img":         self.info_project_img_edit.text().strip(),
            "include_project_info":  self.include_project_info_cb.isChecked(),
            "include_doc_metadata":  self.include_doc_metadata_cb.isChecked(),
            "include_doc_control":   self.include_doc_control_cb.isChecked(),
            "created_by_name":     self.info_created_by_name_edit.text().strip(),
        }
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                info[f"{role}_{part}"] = getattr(self, f"info_{role}_{part}_edit").text().strip()
        return {
            "layer_names":           self._checked_layer_names(),
            "include_layer_control": self.layer_control_cb.isChecked(),
            "include_basemap":       self.basemap_cb.isChecked(),
            "initial_extent":        self._initial_extent,
            "map_views":             self._map_views,
            "output_path":           self.path_edit.text().strip(),
            "info":                  info,
            "theme":                 self.export_theme_combo.currentData(),
        }

    def _apply_state(self, state):
        self.layer_control_cb.setChecked(bool(state.get("include_layer_control", True)))
        self.basemap_cb.setChecked(bool(state.get("include_basemap", False)))
        ext = state.get("initial_extent")
        if ext:
            self._initial_extent = ext
            self._update_initial_extent_label()
        self._map_views = [dict(mv) for mv in state.get("map_views", [])]
        self._map_view_clear_form()
        self._map_views_list_refresh()
        self._mv_update_rubber_bands()
        out = state.get("output_path", "")
        if out:
            self.path_edit.setText(out)

        info = state.get("info", {})
        self.include_info_cb.setChecked(bool(info.get("enabled", True)))
        self.info_title_edit.setText(info.get("title", ""))
        self.info_text_edit.setPlainText(info.get("text", ""))
        self.info_doc_number_edit.setText(info.get("doc_number", ""))
        self.info_revision_edit.setText(info.get("revision", ""))

        purpose = info.get("purpose", "")
        idx = self.info_purpose_combo.findText(purpose)
        if idx >= 0:
            self.info_purpose_combo.setCurrentIndex(idx)
        else:
            self.info_purpose_combo.setEditText(purpose)

        self.info_client_edit.setText(info.get("client", ""))
        self.info_client_img_edit.setText(info.get("client_img", ""))
        self.info_project_number_edit.setText(info.get("project_number", ""))
        self.info_project_edit.setText(info.get("project", ""))
        self.info_project_img_edit.setText(info.get("project_img", ""))
        self.include_project_info_cb.setChecked(bool(info.get("include_project_info", True)))
        self.include_doc_metadata_cb.setChecked(bool(info.get("include_doc_metadata", True)))
        self.include_doc_control_cb.setChecked(bool(info.get("include_doc_control", True)))
        self.info_created_by_name_edit.setText(info.get("created_by_name", ""))

        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                getattr(self, f"info_{role}_{part}_edit").setText(info.get(f"{role}_{part}", ""))

        self._set_checked_layers_by_name(state.get("layer_names", []))
        theme_val = state.get("theme", "corporate")
        idx = self.export_theme_combo.findData(theme_val)
        if idx >= 0:
            self.export_theme_combo.setCurrentIndex(idx)

    def _instance_load(self, name=None):
        if name is None:
            return
        data = self._instances_load_all()
        state = data.get(name)
        if state is None:
            QMessageBox.warning(self, "Not found", f"Config '{name}' could not be found.")
            return
        self._apply_state(state)
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        self._update_config_bar()
        missing = self._missing_layer_names(state.get("layer_names", []))
        if missing:
            QMessageBox.information(
                self, "Loaded with missing layers",
                "Config '{}' loaded.\n\nThe following layers are not in the current "
                "project and were skipped:\n  • {}".format(name, "\n  • ".join(missing))
            )

    def _instance_save(self):
        name = self._loaded_instance_name
        if not name:
            self._instance_save_as()
            return
        data = self._instances_load_all()
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._has_unsaved_changes = False
        self._update_config_bar()
        self.iface.messageBar().pushInfo("InterCarta", f"Config '{name}' saved.")

    def _instance_save_as(self):
        name, ok = QInputDialog.getText(self, "Save config as", "Config name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Please enter a name for the config.")
            return
        data = self._instances_load_all()
        if name in data:
            resp = QMessageBox.question(
                self, "Overwrite?",
                f"A config named '{name}' already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        self._update_config_bar()
        self.iface.messageBar().pushInfo("InterCarta", f"Config '{name}' saved.")

    def _instance_delete(self):
        name = self._loaded_instance_name
        if not name:
            return
        resp = QMessageBox.question(
            self, "Delete config",
            f"Delete saved config '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        data = self._instances_load_all()
        data.pop(name, None)
        self._instances_save_all(data)
        self._loaded_instance_name = None
        self._has_unsaved_changes = False
        self._update_config_bar()

    # ── Layer tree ────────────────────────────────────────────────────────────

    def _get_required_layer_names(self):
        """Return the set of layer names referenced by any map view (static or theme)."""
        required = set()
        for mv in self._map_views:
            for name in mv.get("layerIds", []):
                required.add(name)
            theme_name = mv.get("theme")
            if theme_name:
                try:
                    tc = QgsProject.instance().mapThemeCollection()
                    for layer in tc.mapThemeVisibleLayers(theme_name):
                        required.add(layer.name())
                except Exception:
                    pass
        return required

    def _update_required_layers(self):
        """Re-apply lock styling to any layer that is referenced by a map view."""
        required = self._get_required_layer_names()
        self.layer_tree_widget.blockSignals(True)

        def walk(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.UserRole)
                if layer_id is not None:
                    layer = QgsProject.instance().mapLayer(layer_id)
                    if layer and layer.name() in required:
                        item.setCheckState(0, Qt.Checked)
                        item.setToolTip(0, "Required by a map view — cannot be deselected")
                        item.setForeground(0, QColor(_AR_PURPLE))
                    else:
                        item.setToolTip(0, "")
                        item.setForeground(0, QColor())  # reset to default
                walk(item)

        walk(self.layer_tree_widget.invisibleRootItem())
        self.layer_tree_widget.blockSignals(False)

    def _on_layer_item_changed(self, item, column):
        if column != 0:
            return
        self.layer_tree_widget.blockSignals(True)
        state = item.checkState(0)

        # Prevent unchecking required layers
        if state == Qt.Unchecked:
            layer_id = item.data(0, Qt.UserRole)
            if layer_id:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer and layer.name() in self._get_required_layer_names():
                    item.setCheckState(0, Qt.Checked)
                    self.layer_tree_widget.blockSignals(False)
                    return

        if state != Qt.PartiallyChecked and item.childCount() > 0:
            self._set_children_check_state(item, state)
        parent = item.parent()
        if parent:
            self._update_parent_check_state(parent)
        self.layer_tree_widget.blockSignals(False)

    def _set_children_check_state(self, parent_item, state):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)
            if child.childCount() > 0:
                self._set_children_check_state(child, state)

    def _update_parent_check_state(self, item):
        total = item.childCount()
        if total == 0:
            return
        checked = sum(1 for i in range(total) if item.child(i).checkState(0) == Qt.Checked)
        partial = sum(1 for i in range(total) if item.child(i).checkState(0) == Qt.PartiallyChecked)
        if checked == total:
            item.setCheckState(0, Qt.Checked)
        elif checked == 0 and partial == 0:
            item.setCheckState(0, Qt.Unchecked)
        else:
            item.setCheckState(0, Qt.PartiallyChecked)
        grandparent = item.parent()
        if grandparent:
            self._update_parent_check_state(grandparent)

    def _populate_layers(self):
        self.layer_tree_widget.blockSignals(True)
        self.layer_tree_widget.clear()
        root = QgsProject.instance().layerTreeRoot()

        def add_nodes(parent, node):
            for child in node.children():
                if isinstance(child, QgsLayerTreeGroup):
                    grp = QTreeWidgetItem(parent)
                    grp.setText(0, child.name())
                    grp.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    grp.setCheckState(0, Qt.Unchecked)
                    add_nodes(grp, child)
                    self._update_parent_check_state(grp)
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer is None:
                        continue
                    if layer.type() not in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
                        continue
                    item = QTreeWidgetItem(parent)
                    item.setText(0, layer.name())
                    item.setData(0, Qt.UserRole, layer.id())
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    item.setCheckState(0, Qt.Checked if child.isVisible() else Qt.Unchecked)

        add_nodes(self.layer_tree_widget, root)
        self.layer_tree_widget.expandAll()
        self.layer_tree_widget.blockSignals(False)
        self._populate_qgis_theme_combos()
        self._mv_populate_layer_combo()
        self._update_required_layers()

    def _populate_qgis_theme_combos(self):
        theme_names = []
        try:
            theme_collection = QgsProject.instance().mapThemeCollection()
            theme_names = list(theme_collection.mapThemes())
        except Exception:
            pass
        for combo in (self.qgis_theme_combo, self.import_theme_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— Select QGIS theme —", "")
            for name in theme_names:
                combo.addItem(name, name)
            combo.blockSignals(False)

    def _on_qgis_theme_combo_changed(self, index):
        theme_name = self.qgis_theme_combo.itemData(index)
        if not theme_name:
            return
        self._apply_qgis_theme_to_tree(theme_name)

    def _apply_qgis_theme_to_tree(self, theme_name):
        try:
            theme_collection = QgsProject.instance().mapThemeCollection()
            visible_layers = theme_collection.mapThemeVisibleLayers(theme_name)
            visible_ids = {layer.id() for layer in visible_layers}
        except Exception as e:
            QMessageBox.warning(self, "Theme error", str(e))
            return
        self.layer_tree_widget.blockSignals(True)

        def update_item(item):
            layer_id = item.data(0, Qt.UserRole)
            if layer_id is not None:
                item.setCheckState(0, Qt.Checked if layer_id in visible_ids else Qt.Unchecked)
            else:
                for i in range(item.childCount()):
                    update_item(item.child(i))
                self._update_parent_check_state(item)

        root = self.layer_tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            update_item(root.child(i))
        self.layer_tree_widget.blockSignals(False)
        self.qgis_theme_combo.blockSignals(True)
        self.qgis_theme_combo.setCurrentIndex(0)
        self.qgis_theme_combo.blockSignals(False)

    def _select_all(self):
        self.layer_tree_widget.blockSignals(True)
        self._set_children_check_state(self.layer_tree_widget.invisibleRootItem(), Qt.Checked)
        self.layer_tree_widget.blockSignals(False)

    def _deselect_all(self):
        self.layer_tree_widget.blockSignals(True)
        self._set_children_check_state(self.layer_tree_widget.invisibleRootItem(), Qt.Unchecked)
        self.layer_tree_widget.blockSignals(False)

    def _checked_layer_names(self):
        names = []

        def walk(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.UserRole)
                if layer_id is not None:
                    if item.checkState(0) == Qt.Checked:
                        layer = QgsProject.instance().mapLayer(layer_id)
                        if layer:
                            names.append(layer.name())
                else:
                    walk(item)

        walk(self.layer_tree_widget.invisibleRootItem())
        return names

    def _missing_layer_names(self, names):
        present = set()

        def walk(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.UserRole)
                if layer_id is not None:
                    layer = QgsProject.instance().mapLayer(layer_id)
                    if layer:
                        present.add(layer.name())
                else:
                    walk(item)

        walk(self.layer_tree_widget.invisibleRootItem())
        return [n for n in names if n not in present]

    def _set_checked_layers_by_name(self, names):
        nameset = set(names)
        self.layer_tree_widget.blockSignals(True)

        def walk(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.UserRole)
                if layer_id is not None:
                    layer = QgsProject.instance().mapLayer(layer_id)
                    checked = layer is not None and layer.name() in nameset
                    item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                else:
                    walk(item)

        walk(self.layer_tree_widget.invisibleRootItem())
        root = self.layer_tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child.childCount() > 0:
                self._update_parent_check_state(child)
        self.layer_tree_widget.blockSignals(False)

    def _update_initial_extent_label(self):
        pass  # label removed; _initial_extent still used in export

    def _recapture_initial_extent(self):
        self._initial_extent = self._capture_canvas_extent()

    def _save_to_downloads(self):
        self.path_edit.setText(self._default_output_path())

    # ── Map Views ─────────────────────────────────────────────────────────────

    def _map_views_list_refresh(self):
        from qgis.PyQt.QtWidgets import QListWidgetItem
        from qgis.PyQt.QtGui import QFont
        self.map_views_list_widget.blockSignals(True)
        self.map_views_list_widget.clear()

        # Always-present Default item
        default_item = QListWidgetItem("  Default – No map views")
        default_item.setData(Qt.UserRole, -1)
        default_item.setToolTip("Default map state — click to configure initial extent")
        f = default_item.font()
        f.setItalic(True)
        default_item.setFont(f)
        default_item.setForeground(QColor("#9CA3AF"))
        default_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.map_views_list_widget.addItem(default_item)

        for i, mv in enumerate(self._map_views):
            item = QListWidgetItem("⠿  " + (mv.get("name") or "(unnamed)"))
            item.setData(Qt.UserRole, i)
            item.setToolTip("Drag to reorder")
            self.map_views_list_widget.addItem(item)

        self.map_views_list_widget.blockSignals(False)

    def _on_map_view_selected(self, row):
        item = self.map_views_list_widget.item(row) if row >= 0 else None
        if item and item.data(Qt.UserRole) == -1:
            # Default item
            self._editing_map_view_idx = None
            self.mv_default_detail.setVisible(True)
            self.mv_detail_scroll.setVisible(False)
            self._mv_update_rubber_bands()
            return
        # Adjust for the Default item at position 0
        mv_idx = row - 1
        if row < 1 or mv_idx >= len(self._map_views):
            self._map_view_clear_form()
            self.mv_default_detail.setVisible(False)
            self.mv_detail_scroll.setVisible(False)
            self._mv_update_rubber_bands()
            return
        self.mv_default_detail.setVisible(False)
        self.mv_detail_scroll.setVisible(True)
        mv = self._map_views[mv_idx]
        self._editing_map_view_idx = mv_idx
        self._editing_map_view_extent = mv.get("extent")
        self.map_view_name_edit.blockSignals(True)
        self.map_view_notes_edit.blockSignals(True)
        self.map_view_name_edit.setText(mv.get("name", ""))
        self.map_view_notes_edit.setPlainText(mv.get("notes", ""))
        self.map_view_name_edit.blockSignals(False)
        self.map_view_notes_edit.blockSignals(False)
        self._update_mv_extent_label(mv.get("extent"))
        self._update_mv_layers_label(mv.get("layerIds"), mv.get("theme"))
        self._mv_update_rubber_bands()

    def _update_mv_extent_label(self, ext):
        if ext:
            self.map_view_extent_label.setText(
                f"S={ext[0][0]:.4f} W={ext[0][1]:.4f} "
                f"N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.map_view_extent_label.setText("(not set)")

    def _update_mv_layers_label(self, layer_ids, theme=None):
        if theme:
            self.map_view_layers_label.setText(f"Theme: {theme}")
        elif layer_ids:
            n = len(layer_ids)
            preview = ", ".join(layer_ids[:3])
            suffix = f", +{n-3} more" if n > 3 else ""
            self.map_view_layers_label.setText(f"{n} layer(s): {preview}{suffix}")
        else:
            self.map_view_layers_label.setText("Layers: (not set)")

    def _map_view_clear_form(self):
        self._editing_map_view_idx = None
        self._editing_map_view_extent = None
        self.map_view_name_edit.blockSignals(True)
        self.map_view_notes_edit.blockSignals(True)
        self.map_view_name_edit.clear()
        self.map_view_notes_edit.clear()
        self.map_view_name_edit.blockSignals(False)
        self.map_view_notes_edit.blockSignals(False)
        self.map_view_extent_label.setText("(not set)")
        self.map_view_layers_label.setText("Layers: (not set)")

    def _mv_autosave(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        mv = self._map_views[idx]
        name = self.map_view_name_edit.text().strip()
        mv["name"] = name or mv.get("name", "(unnamed)")
        mv["notes"] = self.map_view_notes_edit.toPlainText().strip()
        self.map_views_list_widget.blockSignals(True)
        item = self.map_views_list_widget.item(idx + 1)  # +1 for Default item at 0
        if item:
            item.setText("⠿  " + mv["name"])
        self.map_views_list_widget.blockSignals(False)

    def _map_view_capture_extent(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        ext = self._capture_canvas_extent()
        self._editing_map_view_extent = ext
        self._update_mv_extent_label(ext)
        if ext is not None:
            self._map_views[idx]["extent"] = ext
            self._mv_update_rubber_bands()

    def _map_view_capture_layers(self):
        try:
            root = QgsProject.instance().layerTreeRoot()
            layer_names = [
                child.layer().name()
                for child in root.findLayers()
                if child.isVisible() and child.layer()
            ]
        except Exception as e:
            QMessageBox.warning(self, "Capture error", str(e))
            return
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        self._map_views[idx]["layerIds"] = layer_names
        self._map_views[idx].pop("theme", None)
        self._update_mv_layers_label(layer_names)
        self._update_required_layers()

    def _map_view_use_theme(self):
        theme_name = self.import_theme_combo.currentData()
        if not theme_name:
            QMessageBox.information(self, "No theme selected", "Select a QGIS theme first.")
            return
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        # Store theme name only — visibility is resolved dynamically at export time
        self._map_views[idx]["theme"] = theme_name
        self._map_views[idx].pop("layerIds", None)
        self._update_mv_layers_label(None, theme=theme_name)
        self._update_required_layers()

    def _map_view_add(self):
        mv = {"name": "New map view", "notes": "", "extent": None, "layerIds": []}
        self._map_views.append(mv)
        self._map_views_list_refresh()
        new_row = len(self._map_views)  # +1 for Default at 0, but count = len+1, last = len
        self.map_views_list_widget.setCurrentRow(new_row)
        self.map_view_name_edit.selectAll()
        self.map_view_name_edit.setFocus()
        self._update_required_layers()

    def _map_view_add_from_theme(self):
        theme_names = []
        try:
            tc = QgsProject.instance().mapThemeCollection()
            theme_names = sorted(tc.mapThemes())
        except Exception:
            pass
        if not theme_names:
            QMessageBox.information(self, "No themes", "No QGIS map themes found in this project.")
            return
        name, ok = QInputDialog.getItem(
            self, "Add map view from theme", "Select a QGIS map theme:", theme_names, 0, False
        )
        if not ok or not name:
            return
        mv = {"name": name, "notes": "", "extent": None, "layerIds": [], "theme": name}
        self._map_views.append(mv)
        self._map_views_list_refresh()
        new_row = self.map_views_list_widget.count() - 1
        self.map_views_list_widget.setCurrentRow(new_row)
        self._update_required_layers()

    def _map_view_delete(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        name = self._map_views[idx].get("name", "this map view")
        resp = QMessageBox.question(
            self, "Delete map view",
            f"Delete '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        del self._map_views[idx]
        self._mv_clear_rubber_bands()
        self._map_views_list_refresh()
        # Select adjacent view or Default
        if self._map_views:
            new_row = min(idx + 1, len(self._map_views))  # +1 for Default
            self.map_views_list_widget.setCurrentRow(new_row)
        else:
            self.map_views_list_widget.setCurrentRow(0)  # Select Default
        self._update_required_layers()

    # ── Browse / Export ───────────────────────────────────────────────────────

    def _browse_image(self, target_edit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp);;All files (*)"
        )
        if path:
            target_edit.setText(path)

    def _browse(self):
        current = self.path_edit.text().strip()
        start_dir = os.path.dirname(current) if current else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save InterCarta Package", start_dir, "HTML Files (*.html);;All Files (*)"
        )
        if path:
            if not path.lower().endswith(".html"):
                path += ".html"
            self.path_edit.setText(path)

    def _export(self):
        output_path = self.path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "No output file", "Please select an output file path.")
            return

        selected_ids = []

        def collect_checked(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.UserRole)
                if layer_id is not None:
                    if item.checkState(0) == Qt.Checked:
                        selected_ids.append(layer_id)
                else:
                    collect_checked(item)

        collect_checked(self.layer_tree_widget.invisibleRootItem())

        if not selected_ids:
            QMessageBox.warning(self, "No layers", "Please select at least one layer to export.")
            return

        selected_id_set = set(selected_ids)
        panel_layers = []
        tree_nodes = []

        def walk(node, out):
            for child in node.children():
                if isinstance(child, QgsLayerTreeGroup):
                    grp_children = []
                    walk(child, grp_children)
                    if grp_children:
                        out.append({"type": "group", "name": child.name(), "children": grp_children})
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer and layer.id() in selected_id_set:
                        out.append({"type": "layer", "index": len(panel_layers)})
                        panel_layers.append(layer)

        walk(QgsProject.instance().layerTreeRoot(), tree_nodes)
        layers = list(reversed(panel_layers))

        self.export_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(layers) + 1)
        self.progress.setValue(0)

        try:
            from .exporter import WebMapExporter
            info_panel = None
            if self.include_info_cb.isChecked():
                today = datetime.datetime.now().strftime("%d/%m/%Y")
                inc_dc   = self.include_doc_control_cb.isChecked()
                inc_proj = self.include_project_info_cb.isChecked()
                inc_dm   = self.include_doc_metadata_cb.isChecked()

                created_by = ""
                if not inc_dc:
                    by_name = self.info_created_by_name_edit.text().strip()
                    created_by = (
                        f"Created by {by_name} on {today}" if by_name
                        else f"Created on {today}"
                    )

                info_panel = {
                    "enabled":         True,
                    "title":           self.info_title_edit.text().strip(),
                    "text":            self.info_text_edit.toPlainText().strip(),
                    "doc_number":      self.info_doc_number_edit.text().strip() if inc_dm else "",
                    "revision":        self.info_revision_edit.text().strip()   if inc_dm else "",
                    "purpose":         self.info_purpose_combo.currentText().strip() if inc_dm else "",
                    "client":          self.info_client_edit.text().strip()          if inc_proj else "",
                    "client_img":      self.info_client_img_edit.text().strip()      if inc_proj else "",
                    "project_number":  self.info_project_number_edit.text().strip()  if inc_proj else "",
                    "project":         self.info_project_edit.text().strip()          if inc_proj else "",
                    "project_img":     self.info_project_img_edit.text().strip()      if inc_proj else "",
                    "include_doc_control": inc_dc,
                    "created_by":      created_by,
                    "date":            today if not inc_dc else "",
                    "originated_name": self.info_originated_name_edit.text().strip() if inc_dc else "",
                    "originated_date": self.info_originated_date_edit.text().strip() if inc_dc else "",
                    "checked_name":    self.info_checked_name_edit.text().strip()    if inc_dc else "",
                    "checked_date":    self.info_checked_date_edit.text().strip()    if inc_dc else "",
                    "reviewed_name":   self.info_reviewed_name_edit.text().strip()   if inc_dc else "",
                    "reviewed_date":   self.info_reviewed_date_edit.text().strip()   if inc_dc else "",
                    "approved_name":   self.info_approved_name_edit.text().strip()   if inc_dc else "",
                    "approved_date":   self.info_approved_date_edit.text().strip()   if inc_dc else "",
                }

            exporter = WebMapExporter(
                layers=layers,
                output_path=output_path,
                include_layer_control=self.layer_control_cb.isChecked(),
                include_basemap=self.basemap_cb.isChecked(),
                progress_callback=lambda v: self.progress.setValue(v),
                layer_tree=tree_nodes,
                initial_extent=self._initial_extent,
                map_views=self._map_views,
                info_panel=info_panel,
                theme=self.export_theme_combo.currentData(),
            )
            exporter.export()
            self._save_settings()
            if self.save_config_on_export_cb.isChecked():
                self._instance_save()
            self._show_success(output_path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            self.export_btn.setEnabled(True)
            self.progress.setVisible(False)

    def _show_success(self, output_path):
        msg = QMessageBox(self)
        msg.setWindowTitle("Export complete")
        msg.setIcon(QMessageBox.Information)
        msg.setText(f"Web map exported successfully to:\n{output_path}")
        open_btn = msg.addButton("Open in Browser", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Ok)
        msg.exec_()
        if msg.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))
