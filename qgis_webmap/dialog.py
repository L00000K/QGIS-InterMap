import os
import json
import datetime
from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QLineEdit,
    QMessageBox, QProgressBar, QCheckBox, QGroupBox,
    QTabWidget, QTextEdit, QFormLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QComboBox, QInputDialog,
)
from qgis.PyQt.QtCore import Qt, QStandardPaths, QUrl, QSettings
from qgis.PyQt.QtGui import QDesktopServices
from qgis.core import QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer

_SETTINGS_KEY = "QgsWebMapExporter"
_INSTANCES_KEY = f"{_SETTINGS_KEY}/instances"  # legacy global key (kept for migration)


class WebMapExportDialog(QDockWidget):
    """Dockable Web Map export panel with a saved-instance manager."""

    def __init__(self, iface, parent=None):
        super().__init__("Export to Web Map", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("WebMapExportPanel")
        self.setMinimumWidth(420)
        self._initial_extent = self._capture_canvas_extent()
        self._map_views = []
        self._editing_map_view_idx = None
        self._editing_map_view_extent = None
        self._build_ui()
        self._update_initial_extent_label()
        self.path_edit.setText(self._default_output_path())
        self._populate_layers()
        self._load_settings()
        self._instances_refresh_combo()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def _on_close_clicked(self):
        self._save_settings()
        self.hide()

    # ── Canvas / path helpers ─────────────────────────────────────────────────

    def _capture_canvas_extent(self):
        """Return the current QGIS map canvas extent as [[s,w],[n,e]] in WGS-84."""
        try:
            from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem
            canvas = self.iface.mapCanvas()
            ext = canvas.extent()
            src_crs = canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(ext)
            return [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
        except Exception:
            return None

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

    # ── Settings (last-used state) ──────────────────────────────────────────────

    def _load_settings(self):
        s = QSettings()
        if s.contains(f"{_SETTINGS_KEY}/include_layer_control"):
            self.layer_control_cb.setChecked(
                s.value(f"{_SETTINGS_KEY}/include_layer_control", True, type=bool)
            )
        if s.contains(f"{_SETTINGS_KEY}/include_basemap"):
            self.basemap_cb.setChecked(
                s.value(f"{_SETTINGS_KEY}/include_basemap", False, type=bool)
            )
        if s.contains(f"{_SETTINGS_KEY}/include_info"):
            self.include_info_cb.setChecked(
                s.value(f"{_SETTINGS_KEY}/include_info", True, type=bool)
            )
        title = s.value(f"{_SETTINGS_KEY}/info_title", "")
        if title:
            self.info_title_edit.setText(title)
        text = s.value(f"{_SETTINGS_KEY}/info_text", "")
        if text:
            self.info_text_edit.setPlainText(text)
        date_val = s.value(f"{_SETTINGS_KEY}/info_date", "")
        if date_val:
            self.info_date_edit.setText(date_val)
        for fld in ("info_client", "info_client_img", "info_project", "info_project_img",
                    "info_doc_number", "info_revision", "info_purpose"):
            val = s.value(f"{_SETTINGS_KEY}/{fld}", "")
            if val:
                getattr(self, f"{fld}_edit").setText(val)
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                val = s.value(f"{_SETTINGS_KEY}/info_{role}_{part}", "")
                if val:
                    getattr(self, f"info_{role}_{part}_edit").setText(val)
        theme_val = s.value(f"{_SETTINGS_KEY}/export_theme", "corporate")
        idx = self.export_theme_combo.findData(theme_val)
        if idx >= 0:
            self.export_theme_combo.setCurrentIndex(idx)

    def _save_settings(self):
        s = QSettings()
        s.setValue(f"{_SETTINGS_KEY}/include_layer_control", self.layer_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_basemap", self.basemap_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_info", self.include_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/info_title", self.info_title_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_text", self.info_text_edit.toPlainText().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_date", self.info_date_edit.text().strip())
        for fld in ("info_client", "info_client_img", "info_project", "info_project_img",
                    "info_doc_number", "info_revision", "info_purpose"):
            s.setValue(f"{_SETTINGS_KEY}/{fld}", getattr(self, f"{fld}_edit").text().strip())
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                s.setValue(f"{_SETTINGS_KEY}/info_{role}_{part}",
                           getattr(self, f"info_{role}_{part}_edit").text().strip())
        s.setValue(f"{_SETTINGS_KEY}/export_theme", self.export_theme_combo.currentData())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        # ── Instance manager bar ──────────────────────────────────────────────
        layout.addWidget(self._build_instance_bar())

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Layers ────────────────────────────────────────────────────
        layers_tab = QWidget()
        layers_layout = QVBoxLayout(layers_tab)

        # QGIS theme quick-apply
        theme_row = QHBoxLayout()
        theme_label = QLabel("Apply QGIS theme:")
        self.qgis_theme_combo = QComboBox()
        self.qgis_theme_combo.setToolTip(
            "Select a QGIS map theme to apply its layer visibility to the export list"
        )
        self.qgis_theme_combo.currentIndexChanged.connect(self._on_qgis_theme_combo_changed)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.qgis_theme_combo, 1)
        layers_layout.addLayout(theme_row)

        # Layer tree
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

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        self.layer_control_cb = QCheckBox("Include legend / layer control (toggles + transparency)")
        self.layer_control_cb.setChecked(True)
        options_layout.addWidget(self.layer_control_cb)

        self.basemap_cb = QCheckBox("Include OpenStreetMap basemap")
        self.basemap_cb.setChecked(False)
        options_layout.addWidget(self.basemap_cb)

        view_row = QHBoxLayout()
        recapture_btn = QPushButton("📷 Re-capture initial view")
        recapture_btn.setToolTip(
            "Sets the map's opening extent to the current QGIS canvas view.\n"
            "Default is the view at the time the panel was opened."
        )
        recapture_btn.clicked.connect(self._recapture_initial_extent)
        view_row.addWidget(recapture_btn)
        self.initial_extent_label = QLabel("View: (captured at open)")
        self.initial_extent_label.setWordWrap(True)
        view_row.addWidget(self.initial_extent_label, 1)
        options_layout.addLayout(view_row)
        layers_layout.addWidget(options_group)

        # Output path
        path_group = QGroupBox("Output file")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select output HTML file…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        layers_layout.addWidget(path_group)

        tabs.addTab(layers_tab, "Layers")

        # ── Tab 2: Map Views ─────────────────────────────────────────────────
        map_views_tab = QWidget()
        mv_tab_layout = QVBoxLayout(map_views_tab)

        # ── Top section: list + sidebar buttons ──────────────────────────────
        top_row = QHBoxLayout()

        self.map_views_list_widget = QListWidget()
        self.map_views_list_widget.setMinimumHeight(120)
        self.map_views_list_widget.setMaximumHeight(160)
        self.map_views_list_widget.currentRowChanged.connect(self._on_map_view_selected)
        top_row.addWidget(self.map_views_list_widget, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(2)
        add_mv_btn = QPushButton("＋ Add")
        add_mv_btn.clicked.connect(self._map_view_add)
        del_mv_btn = QPushButton("✕ Delete")
        del_mv_btn.clicked.connect(self._map_view_delete)
        up_btn = QPushButton("↑ Up")
        up_btn.clicked.connect(self._map_view_move_up)
        down_btn = QPushButton("↓ Down")
        down_btn.clicked.connect(self._map_view_move_down)
        btn_col.addWidget(add_mv_btn)
        btn_col.addWidget(del_mv_btn)
        btn_col.addWidget(up_btn)
        btn_col.addWidget(down_btn)
        btn_col.addStretch()
        top_row.addLayout(btn_col)
        mv_tab_layout.addLayout(top_row)

        # ── Bottom section: detail form (auto-save) ──────────────────────────
        detail_group = QGroupBox("Map view details")
        detail_layout = QVBoxLayout(detail_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.map_view_name_edit = QLineEdit()
        self.map_view_name_edit.setPlaceholderText("Map view name")
        self.map_view_name_edit.textChanged.connect(self._mv_autosave)
        name_row.addWidget(self.map_view_name_edit, 1)
        detail_layout.addLayout(name_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("Notes:"))
        self.map_view_notes_edit = QTextEdit()
        self.map_view_notes_edit.setPlaceholderText("Notes shown below map view name")
        self.map_view_notes_edit.setMaximumHeight(60)
        self.map_view_notes_edit.textChanged.connect(self._mv_autosave)
        notes_row.addWidget(self.map_view_notes_edit, 1)
        detail_layout.addLayout(notes_row)

        # Extent
        extent_row = QHBoxLayout()
        capture_ext_btn = QPushButton("📷 Capture extent from QGIS")
        capture_ext_btn.clicked.connect(self._map_view_capture_extent)
        self.map_view_extent_label = QLabel("(not captured)")
        self.map_view_extent_label.setWordWrap(True)
        extent_row.addWidget(capture_ext_btn)
        extent_row.addWidget(self.map_view_extent_label, 1)
        detail_layout.addLayout(extent_row)

        # Layers source
        layers_row = QHBoxLayout()
        layers_row.addWidget(QLabel("Layers:"))
        self.import_theme_combo = QComboBox()
        self.import_theme_combo.setToolTip("Select a QGIS theme to use for this map view's layer visibility")
        use_theme_btn = QPushButton("Use QGIS theme")
        use_theme_btn.clicked.connect(self._map_view_use_theme)
        capture_layers_btn = QPushButton("📷 Capture visible")
        capture_layers_btn.setToolTip("Capture currently visible layers in QGIS as this map view's layer set")
        capture_layers_btn.clicked.connect(self._map_view_capture_layers)
        layers_row.addWidget(self.import_theme_combo, 1)
        layers_row.addWidget(use_theme_btn)
        layers_row.addWidget(capture_layers_btn)
        detail_layout.addLayout(layers_row)

        self.map_view_layers_label = QLabel("Layers: (not set)")
        detail_layout.addWidget(self.map_view_layers_label)

        mv_tab_layout.addWidget(detail_group)
        mv_tab_layout.addStretch()
        tabs.addTab(map_views_tab, "Map Views")

        # ── Tab 3: Map Info ──────────────────────────────────────────────────
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)

        self.include_info_cb = QCheckBox("Include 'About this Map' info panel")
        self.include_info_cb.setChecked(True)
        info_layout.addWidget(self.include_info_cb)

        info_form = QFormLayout()

        self.info_title_edit = QLineEdit()
        self.info_title_edit.setText(QgsProject.instance().baseName() or "")
        self.info_title_edit.setPlaceholderText("Panel title…")
        info_form.addRow("Title:", self.info_title_edit)

        self.info_text_edit = QTextEdit()
        self.info_text_edit.setPlaceholderText("Description / information text…")
        self.info_text_edit.setMinimumHeight(100)
        info_form.addRow("Description:", self.info_text_edit)

        self.info_date_edit = QLineEdit()
        self.info_date_edit.setText(datetime.datetime.now().strftime("%d/%m/%Y"))
        info_form.addRow("Date:", self.info_date_edit)

        self.info_doc_number_edit = QLineEdit()
        self.info_doc_number_edit.setPlaceholderText("Document number…")
        info_form.addRow("Doc number:", self.info_doc_number_edit)

        self.info_revision_edit = QLineEdit()
        self.info_revision_edit.setPlaceholderText("e.g. P1.02…")
        info_form.addRow("Revision:", self.info_revision_edit)

        self.info_purpose_edit = QLineEdit()
        self.info_purpose_edit.setPlaceholderText("e.g. S2 – Suitable for information…")
        info_form.addRow("Purpose of issue:", self.info_purpose_edit)

        info_layout.addLayout(info_form)

        # ── Project / Client ─────────────────────────────────────────────────
        proj_group = QGroupBox("Project")
        proj_form = QFormLayout(proj_group)
        proj_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.info_client_edit = QLineEdit()
        self.info_client_edit.setPlaceholderText("Client name…")
        proj_form.addRow("Client:", self.info_client_edit)

        _client_img_w = QWidget()
        _client_img_l = QHBoxLayout(_client_img_w)
        _client_img_l.setContentsMargins(0, 0, 0, 0)
        self.info_client_img_edit = QLineEdit()
        self.info_client_img_edit.setPlaceholderText("Client image path (optional)…")
        _client_img_btn = QPushButton("…")
        _client_img_btn.setFixedWidth(32)
        _client_img_btn.clicked.connect(lambda: self._browse_image(self.info_client_img_edit))
        _client_img_l.addWidget(self.info_client_img_edit)
        _client_img_l.addWidget(_client_img_btn)
        proj_form.addRow("Client image:", _client_img_w)

        self.info_project_edit = QLineEdit()
        self.info_project_edit.setPlaceholderText("Project name / number…")
        proj_form.addRow("Project:", self.info_project_edit)

        _project_img_w = QWidget()
        _project_img_l = QHBoxLayout(_project_img_w)
        _project_img_l.setContentsMargins(0, 0, 0, 0)
        self.info_project_img_edit = QLineEdit()
        self.info_project_img_edit.setPlaceholderText("Project image path (optional)…")
        _project_img_btn = QPushButton("…")
        _project_img_btn.setFixedWidth(32)
        _project_img_btn.clicked.connect(lambda: self._browse_image(self.info_project_img_edit))
        _project_img_l.addWidget(self.info_project_img_edit)
        _project_img_l.addWidget(_project_img_btn)
        proj_form.addRow("Project image:", _project_img_w)

        info_layout.addWidget(proj_group)

        # ── Document control block ───────────────────────────────────────────
        from qgis.PyQt.QtWidgets import QGridLayout
        dc_group = QGroupBox("Document Control")
        dc_grid = QGridLayout(dc_group)
        dc_grid.addWidget(QLabel(""), 0, 0)
        dc_grid.addWidget(QLabel("<b>Name</b>"), 0, 1)
        dc_grid.addWidget(QLabel("<b>Date</b>"), 0, 2)
        for label_obj in dc_grid.findChildren(QLabel):
            label_obj.setTextFormat(Qt.RichText)
        _dc_roles = [("Originated", "originated"), ("Checked", "checked"),
                     ("Reviewed", "reviewed"), ("Approved", "approved")]
        for row_i, (label_text, key) in enumerate(_dc_roles, start=1):
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
        info_layout.addWidget(dc_group)
        info_layout.addStretch()

        tabs.addTab(info_tab, "Map Info")

        # ── Tab 4: Style ─────────────────────────────────────────────────────
        style_tab = QWidget()
        style_layout = QVBoxLayout(style_tab)

        theme_group = QGroupBox("Map theme")
        theme_form = QFormLayout(theme_group)
        self.export_theme_combo = QComboBox()
        self.export_theme_combo.addItem("Modern Corporate", "corporate")
        self.export_theme_combo.addItem("AtkinsRéalis Purple", "purple")
        self.export_theme_combo.addItem("Dark", "dark")
        self.export_theme_combo.setToolTip(
            "Choose the colour theme applied to the exported web map"
        )
        theme_form.addRow("Theme:", self.export_theme_combo)
        style_layout.addWidget(theme_group)
        style_layout.addStretch()

        tabs.addTab(style_tab, "Style")

        # ── Progress + bottom buttons ────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._on_close_clicked)
        bottom.addStretch()
        bottom.addWidget(self.export_btn)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self.setWidget(container)

    def _build_instance_bar(self):
        """Top bar to save / load / delete named export instances."""
        group = QGroupBox("Saved instances")
        outer = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Instance:"))
        self.instance_combo = QComboBox()
        self.instance_combo.setToolTip("Saved export configurations")
        self.instance_combo.setMinimumWidth(140)
        row.addWidget(self.instance_combo, 1)
        load_btn = QPushButton("Load")
        load_btn.setToolTip("Load the selected instance into the panel")
        load_btn.clicked.connect(self._instance_load)
        row.addWidget(load_btn)
        outer.addLayout(row)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setToolTip("Update the selected instance with the current settings")
        save_btn.clicked.connect(self._instance_save)
        save_as_btn = QPushButton("Save As…")
        save_as_btn.setToolTip("Save the current settings as a new named instance")
        save_as_btn.clicked.connect(self._instance_save_as)
        del_btn = QPushButton("Delete")
        del_btn.setToolTip("Delete the selected instance")
        del_btn.clicked.connect(self._instance_delete)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(save_as_btn)
        btn_row.addWidget(del_btn)
        outer.addLayout(btn_row)

        return group

    # ── Instance manager ────────────────────────────────────────────────────────

    def _project_instances_key(self):
        """Return a QSettings key scoped to the current QGIS project file."""
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
        # Migration: load from old global key on first use per project
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
        data = self._instances_load_all()
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        self.instance_combo.addItem("— None —", "")
        for name in sorted(data.keys(), key=str.lower):
            self.instance_combo.addItem(name, name)
        if select_name:
            idx = self.instance_combo.findData(select_name)
            if idx >= 0:
                self.instance_combo.setCurrentIndex(idx)
        self.instance_combo.blockSignals(False)

    def _collect_state(self):
        """Capture all filled-in panel settings as a serialisable dict."""
        info = {
            "enabled": self.include_info_cb.isChecked(),
            "title": self.info_title_edit.text().strip(),
            "text": self.info_text_edit.toPlainText().strip(),
            "date": self.info_date_edit.text().strip(),
            "doc_number": self.info_doc_number_edit.text().strip(),
            "revision": self.info_revision_edit.text().strip(),
            "purpose": self.info_purpose_edit.text().strip(),
            "client": self.info_client_edit.text().strip(),
            "client_img": self.info_client_img_edit.text().strip(),
            "project": self.info_project_edit.text().strip(),
            "project_img": self.info_project_img_edit.text().strip(),
        }
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                info[f"{role}_{part}"] = getattr(self, f"info_{role}_{part}_edit").text().strip()
        return {
            "layer_names": self._checked_layer_names(),
            "include_layer_control": self.layer_control_cb.isChecked(),
            "include_basemap": self.basemap_cb.isChecked(),
            "initial_extent": self._initial_extent,
            "map_views": self._map_views,
            "output_path": self.path_edit.text().strip(),
            "info": info,
            "theme": self.export_theme_combo.currentData(),
        }

    def _apply_state(self, state):
        """Repopulate the panel from a saved instance dict."""
        self.layer_control_cb.setChecked(bool(state.get("include_layer_control", True)))
        self.basemap_cb.setChecked(bool(state.get("include_basemap", False)))

        ext = state.get("initial_extent")
        if ext:
            self._initial_extent = ext
            self._update_initial_extent_label()

        self._map_views = [dict(mv) for mv in state.get("map_views", [])]
        self._map_view_clear_form()
        self._map_views_list_refresh()

        out = state.get("output_path", "")
        if out:
            self.path_edit.setText(out)

        info = state.get("info", {})
        self.include_info_cb.setChecked(bool(info.get("enabled", True)))
        self.info_title_edit.setText(info.get("title", ""))
        self.info_text_edit.setPlainText(info.get("text", ""))
        self.info_date_edit.setText(info.get("date", ""))
        self.info_doc_number_edit.setText(info.get("doc_number", ""))
        self.info_revision_edit.setText(info.get("revision", ""))
        self.info_purpose_edit.setText(info.get("purpose", ""))
        self.info_client_edit.setText(info.get("client", ""))
        self.info_client_img_edit.setText(info.get("client_img", ""))
        self.info_project_edit.setText(info.get("project", ""))
        self.info_project_img_edit.setText(info.get("project_img", ""))
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                getattr(self, f"info_{role}_{part}_edit").setText(info.get(f"{role}_{part}", ""))

        self._set_checked_layers_by_name(state.get("layer_names", []))
        theme_val = state.get("theme", "corporate")
        idx = self.export_theme_combo.findData(theme_val)
        if idx >= 0:
            self.export_theme_combo.setCurrentIndex(idx)

    def _instance_load(self):
        name = self.instance_combo.currentData()
        if not name:
            QMessageBox.information(self, "No instance", "Please select a saved instance to load.")
            return
        data = self._instances_load_all()
        state = data.get(name)
        if state is None:
            QMessageBox.warning(self, "Not found", f"Instance '{name}' could not be found.")
            self._instances_refresh_combo()
            return
        self._apply_state(state)
        missing = self._missing_layer_names(state.get("layer_names", []))
        if missing:
            QMessageBox.information(
                self, "Loaded with missing layers",
                "Instance '{}' loaded.\n\nThe following layers are not in the current "
                "project and were skipped:\n  • {}".format(name, "\n  • ".join(missing))
            )

    def _instance_save(self):
        name = self.instance_combo.currentData()
        if not name:
            # Nothing selected — fall back to Save As
            self._instance_save_as()
            return
        data = self._instances_load_all()
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._instances_refresh_combo(select_name=name)
        self.iface.messageBar().pushInfo("Web Map Exporter", f"Instance '{name}' updated.")

    def _instance_save_as(self):
        name, ok = QInputDialog.getText(self, "Save instance as", "Instance name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Please enter a name for the instance.")
            return
        data = self._instances_load_all()
        if name in data:
            resp = QMessageBox.question(
                self, "Overwrite?",
                f"An instance named '{name}' already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
        data[name] = self._collect_state()
        self._instances_save_all(data)
        self._instances_refresh_combo(select_name=name)
        self.iface.messageBar().pushInfo("Web Map Exporter", f"Instance '{name}' saved.")

    def _instance_delete(self):
        name = self.instance_combo.currentData()
        if not name:
            QMessageBox.information(self, "No instance", "Please select a saved instance to delete.")
            return
        resp = QMessageBox.question(
            self, "Delete instance",
            f"Delete the saved instance '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        data = self._instances_load_all()
        data.pop(name, None)
        self._instances_save_all(data)
        self._instances_refresh_combo()

    # ── Layer tree ────────────────────────────────────────────────────────────

    def _on_layer_item_changed(self, item, column):
        if column != 0:
            return
        self.layer_tree_widget.blockSignals(True)
        state = item.checkState(0)
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
        """Names of all currently checked layers in the Layers tab."""
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
        """Subset of names that don't match any layer in the current tree."""
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
        """Check exactly the layers whose names appear in `names`."""
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
        ext = self._initial_extent
        if ext:
            self.initial_extent_label.setText(
                f"View: S={ext[0][0]:.4f} W={ext[0][1]:.4f} "
                f"N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.initial_extent_label.setText("View: (not captured)")

    def _recapture_initial_extent(self):
        self._initial_extent = self._capture_canvas_extent()
        self._update_initial_extent_label()

    # ── Map Views ─────────────────────────────────────────────────────────────

    def _map_views_list_refresh(self):
        self.map_views_list_widget.blockSignals(True)
        self.map_views_list_widget.clear()
        for mv in self._map_views:
            self.map_views_list_widget.addItem(mv.get("name") or "(unnamed)")
        self.map_views_list_widget.blockSignals(False)

    def _on_map_view_selected(self, row):
        if row < 0 or row >= len(self._map_views):
            self._map_view_clear_form()
            return
        mv = self._map_views[row]
        self._editing_map_view_idx = row
        self._editing_map_view_extent = mv.get("extent")
        # Block signals so we don't trigger _mv_autosave while loading
        self.map_view_name_edit.blockSignals(True)
        self.map_view_notes_edit.blockSignals(True)
        self.map_view_name_edit.setText(mv.get("name", ""))
        self.map_view_notes_edit.setPlainText(mv.get("notes", ""))
        self.map_view_name_edit.blockSignals(False)
        self.map_view_notes_edit.blockSignals(False)
        self._update_mv_extent_label(mv.get("extent"))
        self._update_mv_layers_label(mv.get("layerIds"))

    def _update_mv_extent_label(self, ext):
        if ext:
            self.map_view_extent_label.setText(
                f"S={ext[0][0]:.4f} W={ext[0][1]:.4f} "
                f"N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.map_view_extent_label.setText("(not captured)")

    def _update_mv_layers_label(self, layer_ids):
        if layer_ids:
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
        self.map_view_extent_label.setText("(not captured)")
        self.map_view_layers_label.setText("Layers: (not set)")

    def _mv_autosave(self):
        """Auto-save the currently selected map view when any field changes."""
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            return
        mv = self._map_views[idx]
        name = self.map_view_name_edit.text().strip()
        mv["name"] = name or mv.get("name", "(unnamed)")
        mv["notes"] = self.map_view_notes_edit.toPlainText().strip()
        # Refresh list display to show updated name
        self.map_views_list_widget.blockSignals(True)
        item = self.map_views_list_widget.item(idx)
        if item:
            item.setText(mv["name"])
        self.map_views_list_widget.blockSignals(False)

    def _map_view_capture_extent(self):
        ext = self._capture_canvas_extent()
        self._editing_map_view_extent = ext
        self._update_mv_extent_label(ext)
        if ext is None:
            return
        idx = self._editing_map_view_idx
        if idx is not None and 0 <= idx < len(self._map_views):
            self._map_views[idx]["extent"] = ext

    def _map_view_capture_layers(self):
        """Capture currently visible QGIS layers as this map view's layer set."""
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
        self._update_mv_layers_label(layer_names)

    def _map_view_use_theme(self):
        """Populate layerIds from the selected QGIS theme."""
        theme_name = self.import_theme_combo.currentData()
        if not theme_name:
            QMessageBox.information(self, "No theme selected", "Select a QGIS theme first.")
            return
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select or add a map view first.")
            return
        try:
            theme_collection = QgsProject.instance().mapThemeCollection()
            visible_layers = theme_collection.mapThemeVisibleLayers(theme_name)
            layer_names = [la.name() for la in visible_layers]
        except Exception as e:
            QMessageBox.warning(self, "Theme error", str(e))
            return
        self._map_views[idx]["layerIds"] = layer_names
        self._update_mv_layers_label(layer_names)

    def _map_view_add(self):
        mv = {"name": "New map view", "notes": "", "extent": None, "layerIds": []}
        self._map_views.append(mv)
        self._map_views_list_refresh()
        new_row = len(self._map_views) - 1
        self.map_views_list_widget.setCurrentRow(new_row)
        # Select name text for immediate renaming
        self.map_view_name_edit.selectAll()
        self.map_view_name_edit.setFocus()

    def _map_view_delete(self):
        row = self.map_views_list_widget.currentRow()
        if row < 0:
            return
        del self._map_views[row]
        self._map_views_list_refresh()
        # Select previous item or clear form
        new_row = min(row, len(self._map_views) - 1)
        if new_row >= 0:
            self.map_views_list_widget.setCurrentRow(new_row)
        else:
            self._map_view_clear_form()

    def _map_view_move_up(self):
        row = self.map_views_list_widget.currentRow()
        if row <= 0:
            return
        self._map_views[row - 1], self._map_views[row] = self._map_views[row], self._map_views[row - 1]
        self._map_views_list_refresh()
        self.map_views_list_widget.setCurrentRow(row - 1)

    def _map_view_move_down(self):
        row = self.map_views_list_widget.currentRow()
        if row < 0 or row >= len(self._map_views) - 1:
            return
        self._map_views[row], self._map_views[row + 1] = self._map_views[row + 1], self._map_views[row]
        self._map_views_list_refresh()
        self.map_views_list_widget.setCurrentRow(row + 1)

    def _import_qgis_theme_as_map_view(self):
        """Legacy method — kept for compatibility; use _map_view_use_theme instead."""
        self._map_view_use_theme()

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
            self, "Save Web Map", start_dir, "HTML Files (*.html);;All Files (*)"
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
                info_panel = {
                    "enabled": True,
                    "title": self.info_title_edit.text().strip(),
                    "text": self.info_text_edit.toPlainText().strip(),
                    "date": self.info_date_edit.text().strip(),
                    "doc_number": self.info_doc_number_edit.text().strip(),
                    "revision": self.info_revision_edit.text().strip(),
                    "purpose": self.info_purpose_edit.text().strip(),
                    "client": self.info_client_edit.text().strip(),
                    "client_img": self.info_client_img_edit.text().strip(),
                    "project": self.info_project_edit.text().strip(),
                    "project_img": self.info_project_img_edit.text().strip(),
                    "originated_name": self.info_originated_name_edit.text().strip(),
                    "originated_date": self.info_originated_date_edit.text().strip(),
                    "checked_name": self.info_checked_name_edit.text().strip(),
                    "checked_date": self.info_checked_date_edit.text().strip(),
                    "reviewed_name": self.info_reviewed_name_edit.text().strip(),
                    "reviewed_date": self.info_reviewed_date_edit.text().strip(),
                    "approved_name": self.info_approved_name_edit.text().strip(),
                    "approved_date": self.info_approved_date_edit.text().strip(),
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
