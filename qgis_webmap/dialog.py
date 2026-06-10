import os
import datetime
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QLineEdit,
    QMessageBox, QProgressBar, QCheckBox, QGroupBox,
    QTabWidget, QTextEdit, QFormLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QComboBox,
)
from qgis.PyQt.QtCore import Qt, QStandardPaths, QUrl, QSettings
from qgis.PyQt.QtGui import QDesktopServices
from qgis.core import QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer

_SETTINGS_KEY = "QgsWebMapExporter"


class WebMapExportDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Export to Web Map")
        self.setMinimumWidth(520)
        self._initial_extent = self._capture_canvas_extent()
        self._scenes = []
        self._editing_scene_idx = None
        self._editing_scene_extent = None
        self._build_ui()
        self._update_initial_extent_label()
        self.path_edit.setText(self._default_output_path())
        self._populate_layers()
        self._load_settings()

    def reject(self):
        self._save_settings()
        super().reject()

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

    # ── Settings ──────────────────────────────────────────────────────────────

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
        originator = s.value(f"{_SETTINGS_KEY}/info_originator", "")
        if originator:
            self.info_originator_edit.setText(originator)
        date_val = s.value(f"{_SETTINGS_KEY}/info_date", "")
        if date_val:
            self.info_date_edit.setText(date_val)
        for fld in ("info_client", "info_project"):
            val = s.value(f"{_SETTINGS_KEY}/{fld}", "")
            if val:
                getattr(self, f"{fld}_edit").setText(val)
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                val = s.value(f"{_SETTINGS_KEY}/info_{role}_{part}", "")
                if val:
                    getattr(self, f"info_{role}_{part}_edit").setText(val)

    def _save_settings(self):
        s = QSettings()
        s.setValue(f"{_SETTINGS_KEY}/include_layer_control", self.layer_control_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_basemap", self.basemap_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/include_info", self.include_info_cb.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/info_title", self.info_title_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_text", self.info_text_edit.toPlainText().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_originator", self.info_originator_edit.text().strip())
        s.setValue(f"{_SETTINGS_KEY}/info_date", self.info_date_edit.text().strip())
        for fld in ("info_client", "info_project"):
            s.setValue(f"{_SETTINGS_KEY}/{fld}", getattr(self, f"{fld}_edit").text().strip())
        for role in ("originated", "checked", "reviewed", "approved"):
            for part in ("name", "date"):
                s.setValue(f"{_SETTINGS_KEY}/info_{role}_{part}",
                           getattr(self, f"info_{role}_{part}_edit").text().strip())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
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
            "Default is the view at the time the dialog was opened."
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

        # ── Tab 2: Scenes ────────────────────────────────────────────────────
        scenes_tab = QWidget()
        scenes_layout = QHBoxLayout(scenes_tab)

        # Left: list + management buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.scenes_list_widget = QListWidget()
        self.scenes_list_widget.setMinimumWidth(160)
        self.scenes_list_widget.currentRowChanged.connect(self._on_scene_selected)
        left_layout.addWidget(self.scenes_list_widget)

        scene_btn_row = QHBoxLayout()
        add_scene_btn = QPushButton("＋ Add")
        add_scene_btn.clicked.connect(self._scene_add)
        edit_scene_btn = QPushButton("✎ Edit")
        edit_scene_btn.clicked.connect(self._scene_edit)
        del_scene_btn = QPushButton("✕ Delete")
        del_scene_btn.clicked.connect(self._scene_delete)
        scene_btn_row.addWidget(add_scene_btn)
        scene_btn_row.addWidget(edit_scene_btn)
        scene_btn_row.addWidget(del_scene_btn)
        left_layout.addLayout(scene_btn_row)

        move_btn_row = QHBoxLayout()
        up_btn = QPushButton("↑ Up")
        up_btn.clicked.connect(self._scene_move_up)
        down_btn = QPushButton("↓ Down")
        down_btn.clicked.connect(self._scene_move_down)
        move_btn_row.addWidget(up_btn)
        move_btn_row.addWidget(down_btn)
        left_layout.addLayout(move_btn_row)

        # Import from QGIS theme section
        import_group = QGroupBox("Import from QGIS theme")
        import_layout = QHBoxLayout(import_group)
        self.import_theme_combo = QComboBox()
        self.import_theme_combo.setToolTip("Select a QGIS map theme to import as a scene")
        import_btn = QPushButton("Import as Scene")
        import_btn.clicked.connect(self._import_qgis_theme_as_scene)
        import_layout.addWidget(self.import_theme_combo, 1)
        import_layout.addWidget(import_btn)
        left_layout.addWidget(import_group)

        scenes_layout.addWidget(left_widget)

        # Right: scene editor form
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.scene_name_edit = QLineEdit()
        self.scene_name_edit.setPlaceholderText("Scene name (required)")
        form.addRow("Name:", self.scene_name_edit)

        self.scene_notes_edit = QTextEdit()
        self.scene_notes_edit.setPlaceholderText("Notes shown below scene name in dropdown")
        self.scene_notes_edit.setMaximumHeight(80)
        form.addRow("Notes:", self.scene_notes_edit)

        right_layout.addLayout(form)

        capture_btn = QPushButton("📷 Capture current QGIS view")
        capture_btn.clicked.connect(self._scene_capture_extent)
        right_layout.addWidget(capture_btn)

        self.scene_extent_label = QLabel("Extent: (not captured)")
        self.scene_extent_label.setWordWrap(True)
        right_layout.addWidget(self.scene_extent_label)

        scene_form_btns = QHBoxLayout()
        save_scene_btn = QPushButton("Save scene")
        save_scene_btn.clicked.connect(self._scene_save)
        clear_form_btn = QPushButton("Clear form")
        clear_form_btn.clicked.connect(self._scene_clear_form)
        scene_form_btns.addWidget(save_scene_btn)
        scene_form_btns.addWidget(clear_form_btn)
        right_layout.addLayout(scene_form_btns)
        right_layout.addStretch()

        scenes_layout.addWidget(right_widget, stretch=1)
        tabs.addTab(scenes_tab, "Scenes")

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

        self.info_originator_edit = QLineEdit()
        self.info_originator_edit.setText("AtkinsRéalis")
        info_form.addRow("Originator:", self.info_originator_edit)

        self.info_date_edit = QLineEdit()
        self.info_date_edit.setText(datetime.datetime.now().strftime("%d/%m/%Y"))
        info_form.addRow("Date:", self.info_date_edit)

        info_layout.addLayout(info_form)

        # ── Project / Client ─────────────────────────────────────────────────
        proj_group = QGroupBox("Project")
        proj_form = QFormLayout(proj_group)
        proj_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.info_client_edit = QLineEdit()
        self.info_client_edit.setPlaceholderText("Client name…")
        proj_form.addRow("Client:", self.info_client_edit)
        self.info_project_edit = QLineEdit()
        self.info_project_edit.setPlaceholderText("Project name / number…")
        proj_form.addRow("Project:", self.info_project_edit)
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

        # ── Progress + bottom buttons ────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addStretch()
        bottom.addWidget(self.export_btn)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

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

    # ── Scenes ────────────────────────────────────────────────────────────────

    def _scenes_list_refresh(self):
        self.scenes_list_widget.blockSignals(True)
        self.scenes_list_widget.clear()
        for scene in self._scenes:
            self.scenes_list_widget.addItem(scene.get("name") or "(unnamed)")
        self.scenes_list_widget.blockSignals(False)

    def _on_scene_selected(self, row):
        if row < 0 or row >= len(self._scenes):
            return
        scene = self._scenes[row]
        self._editing_scene_idx = row
        self._editing_scene_extent = scene.get("extent")
        self.scene_name_edit.setText(scene.get("name", ""))
        self.scene_notes_edit.setPlainText(scene.get("notes", ""))
        ext = scene.get("extent")
        if ext:
            self.scene_extent_label.setText(
                f"Extent: S={ext[0][0]:.4f} W={ext[0][1]:.4f} "
                f"N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.scene_extent_label.setText("Extent: (not captured)")

    def _scene_clear_form(self):
        self._editing_scene_idx = None
        self._editing_scene_extent = None
        self.scene_name_edit.clear()
        self.scene_notes_edit.clear()
        self.scene_extent_label.setText("Extent: (not captured)")
        self.scenes_list_widget.clearSelection()

    def _scene_capture_extent(self):
        ext = self._capture_canvas_extent()
        self._editing_scene_extent = ext
        if ext:
            self.scene_extent_label.setText(
                f"Extent: S={ext[0][0]:.4f} W={ext[0][1]:.4f} "
                f"N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.scene_extent_label.setText("Extent: (could not capture)")

    def _scene_checked_layer_names(self):
        """Return names of currently checked layers in the Layers tab."""
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

    def _scene_save(self):
        name = self.scene_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Scene name required", "Please enter a name for the scene.")
            return
        scene = {
            "name": name,
            "notes": self.scene_notes_edit.toPlainText().strip(),
            "extent": self._editing_scene_extent,
            "layerIds": self._scene_checked_layer_names(),
        }
        if self._editing_scene_idx is not None and 0 <= self._editing_scene_idx < len(self._scenes):
            self._scenes[self._editing_scene_idx] = scene
        else:
            self._scenes.append(scene)
            self._editing_scene_idx = len(self._scenes) - 1
        self._scenes_list_refresh()
        self.scenes_list_widget.setCurrentRow(self._editing_scene_idx)

    def _scene_add(self):
        self._scene_clear_form()

    def _scene_edit(self):
        row = self.scenes_list_widget.currentRow()
        if row < 0:
            QMessageBox.information(self, "No scene selected", "Please select a scene to edit.")
            return
        self._on_scene_selected(row)

    def _scene_delete(self):
        row = self.scenes_list_widget.currentRow()
        if row < 0:
            return
        del self._scenes[row]
        self._scene_clear_form()
        self._scenes_list_refresh()

    def _scene_move_up(self):
        row = self.scenes_list_widget.currentRow()
        if row <= 0:
            return
        self._scenes[row - 1], self._scenes[row] = self._scenes[row], self._scenes[row - 1]
        self._scenes_list_refresh()
        self.scenes_list_widget.setCurrentRow(row - 1)

    def _scene_move_down(self):
        row = self.scenes_list_widget.currentRow()
        if row < 0 or row >= len(self._scenes) - 1:
            return
        self._scenes[row], self._scenes[row + 1] = self._scenes[row + 1], self._scenes[row]
        self._scenes_list_refresh()
        self.scenes_list_widget.setCurrentRow(row + 1)

    def _import_qgis_theme_as_scene(self):
        theme_name = self.import_theme_combo.currentData()
        if not theme_name:
            QMessageBox.information(
                self, "No theme selected", "Please select a QGIS theme to import."
            )
            return
        try:
            theme_collection = QgsProject.instance().mapThemeCollection()
            visible_layers = theme_collection.mapThemeVisibleLayers(theme_name)
            layer_names = [la.name() for la in visible_layers]
        except Exception as e:
            QMessageBox.warning(self, "Import error", str(e))
            return
        scene = {
            "name": theme_name,
            "notes": "",
            "extent": None,
            "layerIds": layer_names,
        }
        self._scenes.append(scene)
        self._scenes_list_refresh()
        idx = len(self._scenes) - 1
        self.scenes_list_widget.setCurrentRow(idx)
        self._editing_scene_idx = idx
        self._editing_scene_extent = None
        self.scene_name_edit.setText(theme_name)
        self.scene_notes_edit.clear()
        self.scene_extent_label.setText("Extent: (not captured)")

    # ── Browse / Export ───────────────────────────────────────────────────────

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
                    "originator": self.info_originator_edit.text().strip(),
                    "date": self.info_date_edit.text().strip(),
                    "client": self.info_client_edit.text().strip(),
                    "project": self.info_project_edit.text().strip(),
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
                scenes=self._scenes,
                info_panel=info_panel,
            )
            exporter.export()
            self._save_settings()
            self._show_success(output_path)
            self.accept()
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
