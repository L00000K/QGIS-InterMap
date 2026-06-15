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
from qgis.PyQt.QtGui import (
    QDesktopServices, QPixmap, QColor, QFont, QTextCharFormat,
    QTextListFormat, QTextImageFormat, QTextBlockFormat, QTextLength,
    QTextTableFormat,
)
from qgis.PyQt.QtCore import Qt, QStandardPaths, QUrl, QSettings, pyqtSignal, QBuffer, QByteArray
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

# ── Vertical resize handle for rich-text editors ─────────────────────────────

class _VResizeHandle(QWidget):
    """Thin drag strip that resizes a QTextEdit vertically."""
    def __init__(self, target, min_h=50, parent=None):
        super().__init__(parent)
        self._target = target
        self._drag_y = None
        self._start_h = None
        self._min_h = min_h
        self.setFixedHeight(6)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("Drag to resize")
        self.setStyleSheet("background:#CBD5E1; border-radius:2px; margin:1px 0;")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_y = e.globalPos().y()
            self._start_h = self._target.height()

    def mouseMoveEvent(self, e):
        if self._drag_y is not None:
            delta = e.globalPos().y() - self._drag_y
            self._target.setFixedHeight(max(self._min_h, self._start_h + delta))

    def mouseReleaseEvent(self, e):
        self._drag_y = None

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
    """Dockable InterMap export panel."""

    def __init__(self, iface, parent=None):
        super().__init__("InterMap", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("InterMapPanel")
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

    # ── UI ────────────────────────────────────────────────────────────────────

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

        # Prefer icon.svg; fall back to icon.png
        icon_lbl = QLabel()
        svg_icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        png_icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
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
                if os.path.exists(png_icon_path):
                    pm = QPixmap(png_icon_path).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    icon_lbl.setPixmap(pm)
        elif os.path.exists(png_icon_path):
            pm = QPixmap(png_icon_path).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pm)
        title_row.addWidget(icon_lbl)

        name_lbl = QLabel("InterMap")
        name_lbl.setObjectName("icName")
        title_row.addWidget(name_lbl)
        title_row.addStretch()
        top_vl.addLayout(title_row)
        outer.addWidget(top)

        # ── White strip: descriptions only (no AR logo) ───────────────────────
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

        desc2 = QLabel(
            "This plugin is in open beta — for feature requests, bugs or further info "
            "reach out to Luke.Johnstone@Atkinsrealis.com"
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
                border-bottom: 2px solid {_AR_PURPLE};
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
                color: {_AR_PURPLE};
                border-bottom: 3px solid {_AR_PURPLE};
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
        self.config_name_label.setTextFormat(Qt.RichText)
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
        import html as _h
        loaded = self._loaded_instance_name is not None
        self._config_none_widget.setVisible(not loaded)
        self._config_loaded_widget.setVisible(loaded)
        if loaded:
            label = f"Saved config:  <b>{_h.escape(self._loaded_instance_name)}</b>"
            try:
                inc_proj = self.include_project_info_cb.isChecked()
                proj_num = self.info_project_number_edit.text().strip()
                if inc_proj and proj_num:
                    label += f"   ·   {_h.escape(proj_num)}"
            except AttributeError:
                pass
            self.config_name_label.setText(label)
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
        self.iface.messageBar().pushInfo("InterMap", f"Config '{name}' created.")

    def _show_config_menu(self):
        menu = QMenu(self)
        new_act     = menu.addAction("New blank config…")
        switch_act  = menu.addAction("Switch / Load…")
        save_as_act = menu.addAction("Save As…")
        menu.addSeparator()
        del_act = menu.addAction("Delete")
        btn = self.sender()
        action = menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action == new_act:
            self._new_blank_config()
        elif action == switch_act:
            self._config_bar_load()
        elif action == save_as_act:
            self._instance_save_as()
        elif action == del_act:
            self._instance_delete()

    def _new_blank_config(self):
        name, ok = QInputDialog.getText(self, "New blank config", "Config name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        data = self._instances_load_all()
        if name in data:
            resp = QMessageBox.question(
                self, "Overwrite?", f"Config '{name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
        blank = {"map_views": [{"name": "Default", "notes": "", "extent": None, "layerIds": []}]}
        self._apply_state(blank)  # reset everything to defaults with one Default view
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._update_config_bar()
        self.iface.messageBar().pushInfo("InterMap", f"Config '{name}' created.")

    # ── Rich-text helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _set_richtext(edit, text):
        if text and ("<html" in text[:80] or "<!DOCTYPE" in text[:80]):
            edit.setHtml(text)
        else:
            edit.setPlainText(text or "")

    @staticmethod
    def _richtext_to_body(html):
        import re
        m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
        if m:
            body = m.group(1).strip()
            body = re.sub(r"^<p\s[^>]*>", "<p>", body)
            return body
        return html

    def _make_rt_btn(self, label, tip, checkable=False, width=24, label_style=""):
        """Small toolbar button for rich-text toolbars."""
        btn = QPushButton(label)
        btn.setToolTip(tip)
        btn.setFixedSize(width, 22)
        btn.setCheckable(checkable)
        css = (
            f"QPushButton {{ font-size:10px; padding:0; border:1px solid #D1D5DB; border-radius:2px; {label_style} }}"
            f"QPushButton:checked {{ background:#ede9ff; border-color:{_AR_PURPLE}; }}"
            f"QPushButton:hover {{ border-color:#9CA3AF; }}"
        )
        btn.setStyleSheet(css)
        return btn

    def _wire_fmt_sync(self, edit, b_btn, i_btn, u_btn, s_btn=None):
        """Sync B/I/U/S button checked state to *edit*'s current cursor format."""
        def _sync(_=None):
            fmt = edit.currentCharFormat()
            for btn in [b_btn, i_btn, u_btn, s_btn]:
                if btn:
                    btn.blockSignals(True)
            b_btn.setChecked(fmt.fontWeight() >= QFont.Bold)
            i_btn.setChecked(fmt.fontItalic())
            u_btn.setChecked(fmt.fontUnderline())
            if s_btn:
                s_btn.setChecked(fmt.fontStrikeOut())
            for btn in [b_btn, i_btn, u_btn, s_btn]:
                if btn:
                    btn.blockSignals(False)
        edit.currentCharFormatChanged.connect(_sync)

    def _build_richtext_toolbar(self, edit):
        """Compact B / I / U + ⤢ expand toolbar for inline text fields."""
        bar = QWidget()
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(0, 0, 0, 2)
        hl.setSpacing(2)

        b = self._make_rt_btn("B", "Bold",      checkable=True, label_style="font-weight:bold")
        i = self._make_rt_btn("I", "Italic",    checkable=True, label_style="font-style:italic")
        u = self._make_rt_btn("U", "Underline", checkable=True, label_style="text-decoration:underline")
        for btn in (b, i, u):
            hl.addWidget(btn)

        hl.addStretch()

        expand_btn = self._make_rt_btn("⤢", "Expand editor", width=22)
        hl.addWidget(expand_btn)

        def _apply(_=None):
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold if b.isChecked() else QFont.Normal)
            fmt.setFontItalic(i.isChecked())
            fmt.setFontUnderline(u.isChecked())
            edit.textCursor().mergeCharFormat(fmt)
            edit.mergeCurrentCharFormat(fmt)

        b.clicked.connect(_apply)
        i.clicked.connect(_apply)
        u.clicked.connect(_apply)
        self._wire_fmt_sync(edit, b, i, u)
        expand_btn.clicked.connect(lambda: self._rt_expand(edit))
        return bar

    def _build_full_richtext_toolbar(self, edit):
        """Full rich-text toolbar for the expanded editor panel."""
        bar = QWidget()
        bar.setObjectName("greyBox")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(3)

        def sep():
            s = QLabel("|")
            s.setStyleSheet("color:#D1D5DB; padding:0 2px;")
            hl.addWidget(s)

        # ── Character formatting ──────────────────────────────────────────────
        b = self._make_rt_btn("B", "Bold",          checkable=True, label_style="font-weight:bold")
        i = self._make_rt_btn("I", "Italic",        checkable=True, label_style="font-style:italic")
        u = self._make_rt_btn("U", "Underline",     checkable=True, label_style="text-decoration:underline")
        s = self._make_rt_btn("S", "Strikethrough", checkable=True, label_style="text-decoration:line-through")
        for btn in (b, i, u, s):
            hl.addWidget(btn)

        def _apply_char(_=None):
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold if b.isChecked() else QFont.Normal)
            fmt.setFontItalic(i.isChecked())
            fmt.setFontUnderline(u.isChecked())
            fmt.setFontStrikeOut(s.isChecked())
            edit.textCursor().mergeCharFormat(fmt)
            edit.mergeCurrentCharFormat(fmt)

        for btn in (b, i, u, s):
            btn.clicked.connect(_apply_char)
        self._wire_fmt_sync(edit, b, i, u, s)

        sep()

        # ── Font size ─────────────────────────────────────────────────────────
        size_combo = QComboBox()
        size_combo.setFixedWidth(52)
        size_combo.setEditable(True)
        for sz in ("8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "36", "48"):
            size_combo.addItem(sz)
        size_combo.setCurrentText("10")
        size_combo.setToolTip("Font size")
        hl.addWidget(size_combo)

        def _set_size(txt):
            try:
                pts = float(txt)
                if pts > 0:
                    fmt = QTextCharFormat()
                    fmt.setFontPointSize(pts)
                    edit.textCursor().mergeCharFormat(fmt)
            except ValueError:
                pass

        size_combo.currentTextChanged.connect(_set_size)

        def _sync_size(_=None):
            sz = edit.currentCharFormat().fontPointSize()
            if sz > 0:
                size_combo.blockSignals(True)
                size_combo.setCurrentText(str(int(sz)))
                size_combo.blockSignals(False)

        edit.currentCharFormatChanged.connect(_sync_size)

        # ── Font colour ───────────────────────────────────────────────────────
        colour_btn = self._make_rt_btn("A", "Text colour", width=28, label_style="color:#DC2626;font-weight:bold")
        hl.addWidget(colour_btn)

        def _pick_colour():
            from qgis.PyQt.QtWidgets import QColorDialog
            col = QColorDialog.getColor(edit.currentCharFormat().foreground().color(), self, "Text colour")
            if col.isValid():
                fmt = QTextCharFormat()
                fmt.setForeground(col)
                edit.textCursor().mergeCharFormat(fmt)

        colour_btn.clicked.connect(_pick_colour)

        sep()

        # ── Alignment ─────────────────────────────────────────────────────────
        al = self._make_rt_btn("≡L", "Align left",    checkable=True, width=28)
        ac = self._make_rt_btn("≡C", "Align centre",  checkable=True, width=28)
        ar = self._make_rt_btn("≡R", "Align right",   checkable=True, width=28)
        for btn in (al, ac, ar):
            hl.addWidget(btn)

        def _align(alignment, btn):
            for other in (al, ac, ar):
                other.blockSignals(True)
                other.setChecked(other is btn)
                other.blockSignals(False)
            edit.setAlignment(alignment)

        al.clicked.connect(lambda: _align(Qt.AlignLeft,    al))
        ac.clicked.connect(lambda: _align(Qt.AlignHCenter, ac))
        ar.clicked.connect(lambda: _align(Qt.AlignRight,   ar))
        al.setChecked(True)

        sep()

        # ── Lists ─────────────────────────────────────────────────────────────
        bl = self._make_rt_btn("•≡", "Bullet list",   width=28)
        nl = self._make_rt_btn("1.≡", "Numbered list", width=30)
        hl.addWidget(bl)
        hl.addWidget(nl)

        def _insert_list(style):
            cursor = edit.textCursor()
            fmt = QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(1)
            cursor.createList(fmt)

        bl.clicked.connect(lambda: _insert_list(QTextListFormat.ListDisc))
        nl.clicked.connect(lambda: _insert_list(QTextListFormat.ListDecimal))

        sep()

        # ── Link ──────────────────────────────────────────────────────────────
        link_btn = self._make_rt_btn("🔗", "Insert hyperlink", width=28)
        hl.addWidget(link_btn)

        def _insert_link():
            cursor = edit.textCursor()
            sel_text = cursor.selectedText()
            url, ok = QInputDialog.getText(self, "Insert link", "URL:", text="https://")
            if not ok or not url.strip():
                return
            display, ok2 = QInputDialog.getText(self, "Insert link", "Display text:", text=sel_text or url)
            if not ok2:
                return
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(url.strip())
            fmt.setForeground(QColor(_AR_PURPLE))
            fmt.setFontUnderline(True)
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                cursor.insertText(display or url, fmt)

        link_btn.clicked.connect(_insert_link)

        # ── Image ─────────────────────────────────────────────────────────────
        img_btn = self._make_rt_btn("🖼", "Insert image", width=28)
        hl.addWidget(img_btn)

        def _insert_image():
            import base64
            path, _ = QFileDialog.getOpenFileName(
                self, "Insert image", "",
                "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
            )
            if not path:
                return
            from qgis.PyQt.QtGui import QImage
            img = QImage(path)
            if img.isNull():
                return
            if img.width() > 600:
                img = img.scaledToWidth(600, Qt.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            img.save(buf, "PNG")
            b64 = base64.b64encode(bytes(ba)).decode()
            edit.textCursor().insertHtml(
                f'<img src="data:image/png;base64,{b64}" style="max-width:100%">'
            )

        img_btn.clicked.connect(_insert_image)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_btn = self._make_rt_btn("⊞", "Insert table", width=28)
        hl.addWidget(tbl_btn)

        def _insert_table():
            rows, ok = QInputDialog.getInt(self, "Insert table", "Rows:", 2, 1, 20)
            if not ok:
                return
            cols, ok = QInputDialog.getInt(self, "Insert table", "Columns:", 2, 1, 20)
            if not ok:
                return
            tfmt = QTextTableFormat()
            tfmt.setBorder(1)
            tfmt.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
            tfmt.setCellPadding(4)
            tfmt.setCellSpacing(0)
            tfmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            edit.textCursor().insertTable(rows, cols, tfmt)

        tbl_btn.clicked.connect(_insert_table)

        hl.addStretch()
        return bar

    def _build_rt_expand_widget(self):
        """Full-panel rich-text editor overlay (page 1 of _content_stack)."""
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(4)

        # Header row
        hdr = QWidget()
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(0, 0, 0, 0)
        hdr_l.setSpacing(6)
        back_btn = QPushButton("← Done")
        back_btn.setFixedWidth(72)
        back_btn.clicked.connect(self._rt_collapse)
        hdr_l.addWidget(back_btn)
        self._rt_field_label = QLabel("")
        self._rt_field_label.setStyleSheet("font-weight:600; color:#374151;")
        hdr_l.addWidget(self._rt_field_label, 1)
        vl.addWidget(hdr)

        # The shared editor (document is swapped in _rt_expand)
        self._rt_big_edit = QTextEdit()
        self._rt_big_edit.setAcceptRichText(True)

        vl.addWidget(self._build_full_richtext_toolbar(self._rt_big_edit))
        vl.addWidget(self._rt_big_edit, 1)

        self._rt_source_edit = None  # the compact edit currently expanded
        return widget

    def _rt_expand(self, edit):
        """Swap *edit*'s document into the full-panel editor and show it."""
        self._rt_source_edit = edit
        self._rt_big_edit.setDocument(edit.document())
        # Label: try to find a friendly name from the placeholder text
        label = edit.placeholderText() or "Description"
        self._rt_field_label.setText(f"Editing: {label}")
        self._content_stack.setCurrentIndex(1)
        self._rt_big_edit.setFocus()

    def _rt_collapse(self):
        self._rt_source_edit = None
        self._content_stack.setCurrentIndex(0)

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
        self.info_text_edit.setAcceptRichText(True)
        self.info_text_edit.setPlaceholderText("Description / information text…")
        self.info_text_edit.setFixedHeight(100)
        _desc_w = QWidget()
        _desc_vl = QVBoxLayout(_desc_w)
        _desc_vl.setContentsMargins(0, 0, 0, 0)
        _desc_vl.setSpacing(0)
        _desc_vl.addWidget(self._build_richtext_toolbar(self.info_text_edit))
        _desc_vl.addWidget(self.info_text_edit)
        _desc_vl.addWidget(_VResizeHandle(self.info_text_edit))
        info_form.addRow("Description:", _desc_w)
        layout.addWidget(info_group)

        # ── Document metadata ────────────────────────────────────────────────
        _dm_hdr = QWidget()
        _dm_hdr_l = QHBoxLayout(_dm_hdr)
        _dm_hdr_l.setContentsMargins(0, 4, 0, 0)
        _dm_hdr_l.setSpacing(4)
        self._dm_toggle_btn = QPushButton("▼")
        self._dm_toggle_btn.setFixedSize(18, 18)
        self._dm_toggle_btn.setFlat(True)
        self._dm_toggle_btn.setCheckable(True)
        self._dm_toggle_btn.setChecked(True)
        _dm_hdr_l.addWidget(self._dm_toggle_btn)
        _dm_title_lbl = QLabel("Document metadata")
        _dm_title_lbl.setStyleSheet("font-weight: 600;")
        _dm_hdr_l.addWidget(_dm_title_lbl, 1)
        self.include_doc_metadata_cb = QCheckBox("Include in export")
        self.include_doc_metadata_cb.setChecked(True)
        _dm_hdr_l.addWidget(self.include_doc_metadata_cb)
        layout.addWidget(_dm_hdr)

        self.doc_meta_widget = QGroupBox()
        self.doc_meta_widget.setObjectName("greyBox")
        self.doc_meta_widget.setStyleSheet("QGroupBox { margin-top: 0px; padding-top: 6px; }")
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
        self._dm_toggle_btn.toggled.connect(
            lambda checked: (
                self._dm_toggle_btn.setText("▼" if checked else "▶"),
                self.doc_meta_widget.setVisible(checked),
            )
        )
        self.include_doc_metadata_cb.toggled.connect(self._dm_toggle_btn.setChecked)

        # ── Project information ───────────────────────────────────────────────
        _pi_hdr = QWidget()
        _pi_hdr_l = QHBoxLayout(_pi_hdr)
        _pi_hdr_l.setContentsMargins(0, 4, 0, 0)
        _pi_hdr_l.setSpacing(4)
        self._pi_toggle_btn = QPushButton("▼")
        self._pi_toggle_btn.setFixedSize(18, 18)
        self._pi_toggle_btn.setFlat(True)
        self._pi_toggle_btn.setCheckable(True)
        self._pi_toggle_btn.setChecked(True)
        _pi_hdr_l.addWidget(self._pi_toggle_btn)
        _pi_title_lbl = QLabel("Project information")
        _pi_title_lbl.setStyleSheet("font-weight: 600;")
        _pi_hdr_l.addWidget(_pi_title_lbl, 1)
        self.include_project_info_cb = QCheckBox("Include in export")
        self.include_project_info_cb.setChecked(True)
        _pi_hdr_l.addWidget(self.include_project_info_cb)
        layout.addWidget(_pi_hdr)

        self.proj_info_widget = QGroupBox()
        self.proj_info_widget.setObjectName("greyBox")
        self.proj_info_widget.setStyleSheet("QGroupBox { margin-top: 0px; padding-top: 6px; }")
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
        self._pi_toggle_btn.toggled.connect(
            lambda checked: (
                self._pi_toggle_btn.setText("▼" if checked else "▶"),
                self.proj_info_widget.setVisible(checked),
            )
        )
        self.include_project_info_cb.toggled.connect(self._pi_toggle_btn.setChecked)

        # ── Document control ─────────────────────────────────────────────────
        _dc_hdr = QWidget()
        _dc_hdr_l = QHBoxLayout(_dc_hdr)
        _dc_hdr_l.setContentsMargins(0, 4, 0, 0)
        _dc_hdr_l.setSpacing(4)
        self._dc_toggle_btn = QPushButton("▼")
        self._dc_toggle_btn.setFixedSize(18, 18)
        self._dc_toggle_btn.setFlat(True)
        self._dc_toggle_btn.setCheckable(True)
        self._dc_toggle_btn.setChecked(True)
        _dc_hdr_l.addWidget(self._dc_toggle_btn)
        _dc_title_lbl = QLabel("Document control")
        _dc_title_lbl.setStyleSheet("font-weight: 600;")
        _dc_hdr_l.addWidget(_dc_title_lbl, 1)
        self.include_doc_control_cb = QCheckBox("Include in export")
        self.include_doc_control_cb.setChecked(True)
        _dc_hdr_l.addWidget(self.include_doc_control_cb)
        layout.addWidget(_dc_hdr)

        self.doc_control_widget = QGroupBox()
        self.doc_control_widget.setObjectName("greyBox")
        self.doc_control_widget.setStyleSheet("QGroupBox { margin-top: 0px; padding-top: 6px; }")
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

        self._dc_toggle_btn.toggled.connect(
            lambda checked: (
                self._dc_toggle_btn.setText("▼" if checked else "▶"),
                self.doc_control_widget.setVisible(checked),
            )
        )
        self.include_doc_control_cb.toggled.connect(self._dc_toggle_btn.setChecked)
        self.include_doc_control_cb.toggled.connect(self._on_doc_control_toggled)
        self._on_doc_control_toggled(self.include_doc_control_cb.isChecked())

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
        add_layout_btn = QPushButton("＋  Add from layout")
        add_layout_btn.setToolTip("Create a map view from a QGIS print layout (copies name, extent and layers)")
        add_layout_btn.clicked.connect(self._map_view_add_from_layout)
        add_row.addWidget(add_layout_btn)
        mv_layout.addLayout(add_row)

        # ── Map view detail ───────────────────────────────────────────────────
        self.mv_detail_scroll = QScrollArea()
        self.mv_detail_scroll.setWidgetResizable(True)
        self.mv_detail_scroll.setFrameShape(QScrollArea.NoFrame)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 6, 0, 4)
        detail_layout.setSpacing(6)

        # ── Single grey settings box ──────────────────────────────────────────
        mv_settings_box = QGroupBox("Map view settings")
        mv_settings_box.setObjectName("greyBox")
        box_vl = QVBoxLayout(mv_settings_box)
        box_vl.setSpacing(6)

        # Name + View in canvas on same line
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(QLabel("Name:"))
        self.map_view_name_edit = QLineEdit()
        self.map_view_name_edit.setPlaceholderText("Map view name")
        self.map_view_name_edit.textChanged.connect(self._mv_autosave)
        name_row.addWidget(self.map_view_name_edit, 1)
        view_canvas_btn = QPushButton("🗺  View in canvas")
        view_canvas_btn.clicked.connect(self._mv_view_in_canvas)
        name_row.addWidget(view_canvas_btn)
        box_vl.addLayout(name_row)

        # Description (no fixed height — let it grow; scroll handles overflow)
        box_vl.addWidget(QLabel("Description:"))
        self.map_view_notes_edit = QTextEdit()
        self.map_view_notes_edit.setAcceptRichText(True)
        self.map_view_notes_edit.setPlaceholderText("Description shown in the map viewer")
        self.map_view_notes_edit.setFixedHeight(80)
        self.map_view_notes_edit.textChanged.connect(self._mv_autosave)
        box_vl.addWidget(self._build_richtext_toolbar(self.map_view_notes_edit))
        box_vl.addWidget(self.map_view_notes_edit)
        box_vl.addWidget(_VResizeHandle(self.map_view_notes_edit))

        # Layers: status label (standard text, info bold) + toggle + sub-panel
        self.map_view_layers_label = QLabel("Layers: <b>(not configured)</b>")
        self.map_view_layers_label.setTextFormat(Qt.RichText)
        self.map_view_layers_label.setWordWrap(True)
        box_vl.addWidget(self.map_view_layers_label)

        self._mv_layers_toggle_btn = QPushButton("▶  Set layers")
        self._mv_layers_toggle_btn.setFlat(True)
        self._mv_layers_toggle_btn.setStyleSheet("text-align: left; color: #374151; padding: 2px 0;")
        self._mv_layers_toggle_btn.clicked.connect(self._toggle_mv_layers_panel)
        box_vl.addWidget(self._mv_layers_toggle_btn)

        self.mv_layers_panel = QWidget()
        layers_panel_vl = QVBoxLayout(self.mv_layers_panel)
        layers_panel_vl.setContentsMargins(12, 0, 0, 0)
        layers_panel_vl.setSpacing(4)
        copy_layers_btn = QPushButton("from canvas")
        copy_layers_btn.setToolTip("Snapshot which layers are currently visible in QGIS")
        copy_layers_btn.clicked.connect(self._map_view_capture_layers)
        layers_panel_vl.addWidget(copy_layers_btn)
        link_theme_btn = QPushButton("from theme")
        link_theme_btn.setToolTip("Link this view to a QGIS map theme")
        link_theme_btn.clicked.connect(self._mv_pick_and_link_theme)
        layers_panel_vl.addWidget(link_theme_btn)
        mv_layers_layout_btn = QPushButton("from layout")
        mv_layers_layout_btn.setToolTip("Import layer list from a QGIS print layout's map item")
        mv_layers_layout_btn.clicked.connect(self._mv_layers_from_layout)
        layers_panel_vl.addWidget(mv_layers_layout_btn)
        self.mv_layers_panel.setVisible(False)
        box_vl.addWidget(self.mv_layers_panel)

        # View extent: status label + toggle + sub-panel
        self.map_view_extent_label = QLabel("View extent: <b>(not set)</b>")
        self.map_view_extent_label.setTextFormat(Qt.RichText)
        self.map_view_extent_label.setWordWrap(True)
        box_vl.addWidget(self.map_view_extent_label)

        self._mv_extent_toggle_btn = QPushButton("▶  Set extent")
        self._mv_extent_toggle_btn.setFlat(True)
        self._mv_extent_toggle_btn.setStyleSheet("text-align: left; color: #374151; padding: 2px 0;")
        self._mv_extent_toggle_btn.clicked.connect(self._toggle_mv_extent_panel)
        box_vl.addWidget(self._mv_extent_toggle_btn)

        self.mv_extent_panel = QWidget()
        extent_panel_vl = QVBoxLayout(self.mv_extent_panel)
        extent_panel_vl.setContentsMargins(12, 0, 0, 0)
        extent_panel_vl.setSpacing(4)
        set_canvas_btn = QPushButton("from canvas")
        set_canvas_btn.clicked.connect(self._map_view_capture_extent)
        extent_panel_vl.addWidget(set_canvas_btn)
        draw_btn = QPushButton("draw on canvas")
        draw_btn.setToolTip("Click and drag a rectangle on the map canvas")
        draw_btn.clicked.connect(self._mv_start_draw_extent)
        extent_panel_vl.addWidget(draw_btn)
        mv_ext_layout_btn = QPushButton("from layout")
        mv_ext_layout_btn.setToolTip("Import extent from a QGIS print layout's map item")
        mv_ext_layout_btn.clicked.connect(self._mv_extent_from_layout)
        extent_panel_vl.addWidget(mv_ext_layout_btn)
        layer_ext_row = QHBoxLayout()
        layer_ext_row.setSpacing(6)
        self.mv_layer_extent_combo = QComboBox()
        layer_ext_row.addWidget(self.mv_layer_extent_combo, 1)
        set_layer_ext_btn = QPushButton("from layer")
        set_layer_ext_btn.setFixedWidth(80)
        set_layer_ext_btn.clicked.connect(self._mv_set_from_layer_extent)
        layer_ext_row.addWidget(set_layer_ext_btn)
        extent_panel_vl.addLayout(layer_ext_row)
        self.mv_extent_panel.setVisible(False)
        box_vl.addWidget(self.mv_extent_panel)

        detail_layout.addWidget(mv_settings_box, 1)

        # Duplicate + Delete at the bottom (outside grey box)
        dup_btn = QPushButton("Duplicate map view")
        dup_btn.clicked.connect(self._map_view_duplicate)
        detail_layout.addWidget(dup_btn)

        del_btn = QPushButton("Delete map view")
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
        new_order = []
        for i in range(self.map_views_list_widget.count()):
            orig_idx = self.map_views_list_widget.item(i).data(Qt.UserRole)
            if orig_idx is not None and 0 <= orig_idx < len(self._map_views):
                new_order.append(self._map_views[orig_idx])
        if len(new_order) == len(self._map_views):
            self._map_views = new_order
        for i in range(self.map_views_list_widget.count()):
            self.map_views_list_widget.item(i).setData(Qt.UserRole, i)
        self._mv_update_rubber_bands()
        self._update_required_layers()

    def _toggle_mv_layers_panel(self):
        visible = not self.mv_layers_panel.isVisible()
        self.mv_layers_panel.setVisible(visible)
        self._mv_layers_toggle_btn.setText("▼  Set layers" if visible else "▶  Set layers")

    def _toggle_mv_extent_panel(self):
        visible = not self.mv_extent_panel.isVisible()
        self.mv_extent_panel.setVisible(visible)
        self._mv_extent_toggle_btn.setText("▼  Set extent" if visible else "▶  Set extent")

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
            "InterMap", "Click and drag on the map canvas to draw the extent."
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
        if self._tab_stack.currentIndex() != self._MAP_VIEWS_TAB:
            self._mv_clear_rubber_bands()
            return
        self._mv_clear_rubber_bands()
        try:
            from qgis.gui import QgsRubberBand
        except ImportError:
            return

        canvas = self.iface.mapCanvas()
        selected_idx = self._editing_map_view_idx

        for i, mv in enumerate(self._map_views):
            ext = mv.get("extent")
            if not ext:
                continue
            try:
                transformed = self._wgs84_to_canvas_rect(ext)
                rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
                if i == selected_idx:
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

        theme_group = QGroupBox("Export colour theme")
        theme_form = QFormLayout(theme_group)
        self.export_theme_combo = QComboBox()
        self.export_theme_combo.addItem("Grey / Black", "corporate")
        self.export_theme_combo.addItem("Blue", "purple")
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
            "text":                self.info_text_edit.toHtml(),
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
        raw_views = [dict(mv) for mv in state.get("map_views", [])]
        # Migrate old configs that stored default_mv separately
        old_default = state.get("default_mv")
        if old_default:
            raw_views = [dict(old_default)] + raw_views
        self._map_views = raw_views
        self._map_view_clear_form()
        self._map_views_list_refresh()
        self._mv_update_rubber_bands()
        out = state.get("output_path", "")
        if out:
            self.path_edit.setText(out)

        info = state.get("info", {})
        self.include_info_cb.setChecked(bool(info.get("enabled", True)))
        self.info_title_edit.setText(info.get("title", ""))
        self._set_richtext(self.info_text_edit, info.get("text", ""))
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
        self.iface.messageBar().pushInfo("InterMap", f"Config '{name}' saved.")

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
        self.iface.messageBar().pushInfo("InterMap", f"Config '{name}' saved.")

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

        def walk(item):
            """Return True if this item or any descendant is a required layer."""
            layer_id = item.data(0, Qt.UserRole)
            if layer_id is not None:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer and layer.name() in required:
                    item.setCheckState(0, Qt.Checked)
                    item.setToolTip(0, "Required by a map view — cannot be deselected")
                    item.setForeground(0, QColor(_AR_PURPLE))
                    return True
                else:
                    item.setToolTip(0, "")
                    item.setForeground(0, QColor())
                    return False
            else:
                # Group item — walk children first
                child_required = False
                for i in range(item.childCount()):
                    if walk(item.child(i)):
                        child_required = True
                if child_required:
                    item.setCheckState(0, Qt.Checked)
                    item.setForeground(0, QColor(_AR_PURPLE))
                else:
                    item.setForeground(0, QColor())
                return child_required

        root = self.layer_tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            walk(root.child(i))

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
        self.qgis_theme_combo.blockSignals(True)
        self.qgis_theme_combo.clear()
        self.qgis_theme_combo.addItem("— Select QGIS theme —", "")
        for name in theme_names:
            self.qgis_theme_combo.addItem(name, name)
        self.qgis_theme_combo.blockSignals(False)

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
        root = self.layer_tree_widget.invisibleRootItem()
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

        def sync_groups(item):
            """Post-order: update group check state and expansion from leaves up."""
            has_checked = False
            for i in range(item.childCount()):
                child = item.child(i)
                if child.childCount() > 0:
                    child_has = sync_groups(child)
                else:
                    child_has = child.checkState(0) == Qt.Checked
                has_checked = has_checked or child_has
            if item is not root and item.childCount() > 0:
                total = item.childCount()
                n_checked = sum(1 for j in range(total) if item.child(j).checkState(0) == Qt.Checked)
                n_partial = sum(1 for j in range(total) if item.child(j).checkState(0) == Qt.PartiallyChecked)
                if n_checked == total:
                    item.setCheckState(0, Qt.Checked)
                elif n_checked == 0 and n_partial == 0:
                    item.setCheckState(0, Qt.Unchecked)
                else:
                    item.setCheckState(0, Qt.PartiallyChecked)
                item.setExpanded(has_checked)
            return has_checked

        walk(root)
        sync_groups(root)
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
        self.map_views_list_widget.blockSignals(True)
        self.map_views_list_widget.clear()
        for i, mv in enumerate(self._map_views):
            item = QListWidgetItem("⠿  " + (mv.get("name") or "(unnamed)"))
            item.setData(Qt.UserRole, i)
            item.setToolTip("Drag to reorder")
            self.map_views_list_widget.addItem(item)
        self.map_views_list_widget.blockSignals(False)

    def _on_map_view_selected(self, row):
        if row < 0 or row >= len(self._map_views):
            self._map_view_clear_form()
            self.mv_detail_scroll.setVisible(False)
            self._mv_update_rubber_bands()
            return
        mv = self._map_views[row]
        self._editing_map_view_idx = row
        self.mv_detail_scroll.setVisible(True)
        self._editing_map_view_extent = mv.get("extent")
        self.map_view_name_edit.blockSignals(True)
        self.map_view_notes_edit.blockSignals(True)
        self.map_view_name_edit.setText(mv.get("name", ""))
        self._set_richtext(self.map_view_notes_edit, mv.get("notes", ""))
        self.map_view_name_edit.blockSignals(False)
        self.map_view_notes_edit.blockSignals(False)
        self._update_mv_extent_label(mv.get("extent"))
        self._update_mv_layers_label(mv.get("layerIds"), mv.get("theme"))
        self._mv_update_rubber_bands()

    def _update_mv_extent_label(self, ext):
        if ext:
            self.map_view_extent_label.setText(
                f"View extent: <b>S {ext[0][0]:.4f}  W {ext[0][1]:.4f}  "
                f"N {ext[1][0]:.4f}  E {ext[1][1]:.4f}</b>"
            )
        else:
            self.map_view_extent_label.setText("View extent: <b>(not set)</b>")

    def _update_mv_layers_label(self, layer_ids, theme=None):
        if theme:
            import html as _h
            self.map_view_layers_label.setText(
                f"Layers: <b>slaved to theme — {_h.escape(theme)}</b>"
            )
        elif layer_ids:
            n = len(layer_ids)
            import html as _h
            preview = ", ".join(_h.escape(x) for x in layer_ids[:3])
            suffix = f", +{n-3} more" if n > 3 else ""
            self.map_view_layers_label.setText(
                f"Layers: <b>set manually — {n} layer(s): {preview}{suffix}</b>"
            )
        else:
            self.map_view_layers_label.setText("Layers: <b>(not configured)</b>")

    def _map_view_clear_form(self):
        self._editing_map_view_idx = None
        self._editing_map_view_extent = None
        self.map_view_name_edit.blockSignals(True)
        self.map_view_notes_edit.blockSignals(True)
        self.map_view_name_edit.clear()
        self.map_view_notes_edit.clear()
        self.map_view_name_edit.blockSignals(False)
        self.map_view_notes_edit.blockSignals(False)
        self.map_view_extent_label.setText("View extent: <b>(not set)</b>")
        self.map_view_layers_label.setText("Layers: <b>(not configured)</b>")

    def _mv_autosave(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        mv = self._map_views[idx]
        name = self.map_view_name_edit.text().strip()
        mv["name"] = name or mv.get("name", "(unnamed)")
        mv["notes"] = self.map_view_notes_edit.toHtml()
        self.map_views_list_widget.blockSignals(True)
        item = self.map_views_list_widget.item(idx)
        if item:
            item.setText("⠿  " + mv["name"])
        self.map_views_list_widget.blockSignals(False)

    def _map_view_capture_extent(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
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
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return
        self._map_views[idx]["layerIds"] = layer_names
        self._map_views[idx].pop("theme", None)
        self._update_mv_layers_label(layer_names)
        self._update_required_layers()

    def _mv_pick_and_link_theme(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return
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
            self, "Link to theme", "Select a QGIS map theme:", theme_names, 0, False
        )
        if not ok or not name:
            return
        self._map_views[idx]["theme"] = name
        self._map_views[idx].pop("layerIds", None)
        self._update_mv_layers_label(None, theme=name)
        self._update_required_layers()

    def _map_view_add(self):
        ext = self._capture_canvas_extent()
        mv = {"name": "New map view", "notes": "", "extent": ext, "layerIds": []}
        self._map_views.append(mv)
        self._map_views_list_refresh()
        self.map_views_list_widget.setCurrentRow(len(self._map_views) - 1)
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

    # ── Print layout helpers ──────────────────────────────────────────────────

    def _pick_layout(self):
        """Prompt user to pick a print layout. Returns (QgsPrintLayout, name) or (None, None)."""
        try:
            lm = QgsProject.instance().layoutManager()
            layouts = [l for l in lm.layouts() if hasattr(l, "referenceMap")]
        except Exception:
            layouts = []
        if not layouts:
            QMessageBox.information(self, "No layouts", "No print layouts found in this project.")
            return None, None
        names = [l.name() for l in layouts]
        name, ok = QInputDialog.getItem(self, "Select layout", "Print layout:", names, 0, False)
        if not ok or not name:
            return None, None
        for l in layouts:
            if l.name() == name:
                return l, name
        return None, None

    def _extent_from_layout(self, layout):
        """Return [[s,w],[n,e]] geographic extent from the layout's reference map, or None."""
        try:
            ref = layout.referenceMap()
            if ref is None:
                return None
            rect = ref.extent()
            project_crs = QgsProject.instance().crs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(project_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(rect)
            return [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
        except Exception:
            return None

    def _layers_from_layout(self, layout):
        """
        Inspect the layout's reference map and return one of:
          {"mode": "theme",   "theme": str}       — map item follows a visibility preset
          {"mode": "layers",  "layerIds": [str]}  — map item has a fixed layer override
          {"mode": "project"}                     — map item follows project visibility
        """
        try:
            ref = layout.referenceMap()
            if ref is None:
                return {"mode": "project"}
            # Check whether the map item is linked to a visibility preset (theme)
            if (getattr(ref, "followVisibilityPreset", lambda: False)() and
                    getattr(ref, "followVisibilityPresetName", lambda: "")().strip()):
                return {"mode": "theme", "theme": ref.followVisibilityPresetName()}
            # Check for an explicit layer override
            layers = ref.layers()
            if layers:
                return {"mode": "layers", "layerIds": [l.name() for l in layers if l]}
        except Exception:
            pass
        return {"mode": "project"}

    def _map_view_add_from_layout(self):
        layout, name = self._pick_layout()
        if layout is None:
            return
        ext = self._extent_from_layout(layout)
        layer_info = self._layers_from_layout(layout)
        mv = {"name": name, "notes": "", "extent": ext, "layerIds": []}
        if layer_info["mode"] == "theme":
            mv["theme"] = layer_info["theme"]
        elif layer_info["mode"] == "layers":
            mv["layerIds"] = layer_info["layerIds"]
        self._map_views.append(mv)
        self._map_views_list_refresh()
        new_row = self.map_views_list_widget.count() - 1
        self.map_views_list_widget.setCurrentRow(new_row)
        self._update_required_layers()

    def _mv_extent_from_layout(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return
        layout, _name = self._pick_layout()
        if layout is None:
            return
        ext = self._extent_from_layout(layout)
        if ext is None:
            QMessageBox.warning(self, "No extent", "Could not read extent from the layout's map item.")
            return
        self._editing_map_view_extent = ext
        self._map_views[idx]["extent"] = ext
        self._update_mv_extent_label(ext)
        self._mv_update_rubber_bands()

    def _mv_layers_from_layout(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return
        layout, _name = self._pick_layout()
        if layout is None:
            return
        layer_info = self._layers_from_layout(layout)
        if layer_info["mode"] == "theme":
            theme = layer_info["theme"]
            self._map_views[idx]["layerIds"] = []
            self._map_views[idx]["theme"] = theme
            self._update_mv_layers_label(None, theme=theme)
            self._update_required_layers()
        elif layer_info["mode"] == "layers":
            self._map_views[idx]["layerIds"] = layer_info["layerIds"]
            self._map_views[idx].pop("theme", None)
            self._update_mv_layers_label(layer_info["layerIds"], theme=None)
            self._update_required_layers()
        else:
            QMessageBox.information(
                self, "No layer override",
                "This layout's map item follows the project's layer visibility.\n"
                "Use 'from canvas' to snapshot the current canvas layers instead."
            )

    def _map_view_duplicate(self):
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        import copy
        dupe = copy.deepcopy(self._map_views[idx])
        dupe["name"] = dupe.get("name", "Map view") + " (copy)"
        self._map_views.insert(idx + 1, dupe)
        self._map_views_list_refresh()
        self.map_views_list_widget.setCurrentRow(idx + 1)
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
        if self._map_views:
            self.map_views_list_widget.setCurrentRow(min(idx, len(self._map_views) - 1))
        else:
            self._map_view_clear_form()
            self.mv_detail_scroll.setVisible(False)
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
            self, "Save InterMap Package", start_dir, "HTML Files (*.html);;All Files (*)"
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

        # Warn if any vector layer has very many features
        heavy = [
            f"  {lr.name()}  ({lr.featureCount():,} features)"
            for lr in layers
            if hasattr(lr, "featureCount") and lr.featureCount() > 50_000
        ]
        if heavy:
            msg = (
                "The following layers have a large number of features and may result "
                "in a slow or unresponsive webmap:\n\n"
                + "\n".join(heavy)
                + "\n\nConsider filtering or simplifying before export.\n\nContinue anyway?"
            )
            if QMessageBox.question(self, "Performance warning", msg,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

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
                    "text":            self.info_text_edit.toHtml(),
                    "doc_number":      self.info_doc_number_edit.text().strip() if inc_dm else "",
                    "revision":        self.info_revision_edit.text().strip()   if inc_dm else "",
                    "purpose":         self.info_purpose_combo.currentText().strip() if inc_dm else "",
                    "client":          self.info_client_edit.text().strip()          if inc_proj else "",
                    "client_img":      self.info_client_img_edit.text().strip()      if inc_proj else "",
                    "project_number":  self.info_project_number_edit.text().strip()  if inc_proj else "",
                    "project":         self.info_project_edit.text().strip()          if inc_proj else "",
                    "project_img":     self.info_project_img_edit.text().strip()      if inc_proj else "",
                    "include_doc_control":  inc_dc,
                    "include_project_info": inc_proj,
                    "include_doc_metadata": inc_dm,
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
