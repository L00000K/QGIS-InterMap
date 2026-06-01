import os
import datetime
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QLineEdit,
    QMessageBox, QProgressBar, QCheckBox, QGroupBox,
    QTabWidget, QTextEdit, QFormLayout, QSplitter, QWidget
)
from qgis.PyQt.QtCore import Qt, QStandardPaths, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.core import QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer


class WebMapExportDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Export to Web Map")
        self.setMinimumWidth(480)
        # Capture the current QGIS canvas extent before anything else changes it
        self._initial_extent = self._capture_canvas_extent()
        self._scenes = []
        self._editing_scene_idx = None  # index of scene being edited, or None
        self._build_ui()
        self.path_edit.setText(self._default_output_path())
        self._populate_layers()

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

    # ── Default output path ──────────────────────────────────────────────────

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

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Tab widget ───────────────────────────────────────────────────────
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Layers ────────────────────────────────────────────────────
        layers_tab = QWidget()
        layers_layout = QVBoxLayout(layers_tab)

        # Layer selection
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

        self.layer_list = QListWidget()
        self.layer_list.setMinimumHeight(200)
        layer_layout.addWidget(self.layer_list)
        layers_layout.addWidget(layer_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        self.layer_control_cb = QCheckBox("Include legend / layer control (toggles + transparency)")
        self.layer_control_cb.setChecked(True)
        options_layout.addWidget(self.layer_control_cb)
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

        # Left: list + buttons
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

        scenes_layout.addWidget(left_widget)

        # Right: editor form
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.scene_name_edit = QLineEdit()
        self.scene_name_edit.setPlaceholderText("Scene name (required)")
        form.addRow("Name:", self.scene_name_edit)

        self.scene_title_edit = QLineEdit()
        self.scene_title_edit.setPlaceholderText("Display title")
        form.addRow("Title:", self.scene_title_edit)

        self.scene_notes_edit = QTextEdit()
        self.scene_notes_edit.setPlaceholderText("Notes shown in the map panel")
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

        # ── Progress + bottom buttons (outside tabs) ─────────────────────────
        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Buttons
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

        # Internal state for the scene editor
        self._editing_scene_extent = None

    # ── Scenes helpers ───────────────────────────────────────────────────────

    def _scenes_list_refresh(self):
        """Rebuild the scenes list widget from self._scenes."""
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
        self.scene_title_edit.setText(scene.get("title", ""))
        self.scene_notes_edit.setPlainText(scene.get("notes", ""))
        ext = scene.get("extent")
        if ext:
            self.scene_extent_label.setText(
                f"Extent: S={ext[0][0]:.4f} W={ext[0][1]:.4f} N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.scene_extent_label.setText("Extent: (not captured)")

    def _scene_clear_form(self):
        self._editing_scene_idx = None
        self._editing_scene_extent = None
        self.scene_name_edit.clear()
        self.scene_title_edit.clear()
        self.scene_notes_edit.clear()
        self.scene_extent_label.setText("Extent: (not captured)")
        self.scenes_list_widget.clearSelection()

    def _scene_capture_extent(self):
        """Capture the current QGIS canvas extent and store on the form."""
        ext = self._capture_canvas_extent()
        self._editing_scene_extent = ext
        if ext:
            self.scene_extent_label.setText(
                f"Extent: S={ext[0][0]:.4f} W={ext[0][1]:.4f} N={ext[1][0]:.4f} E={ext[1][1]:.4f}"
            )
        else:
            self.scene_extent_label.setText("Extent: (could not capture)")

    def _scene_checked_layer_names(self):
        """Return the names of currently checked layers in the Layers tab."""
        names = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.data(Qt.UserRole) is not None and item.checkState() == Qt.Checked:
                layer_id = item.data(Qt.UserRole)
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    names.append(layer.name())
        return names

    def _scene_save(self):
        name = self.scene_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Scene name required", "Please enter a name for the scene.")
            return
        scene = {
            "name": name,
            "title": self.scene_title_edit.text().strip(),
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

    def _populate_layers(self):
        self.layer_list.clear()
        root = QgsProject.instance().layerTreeRoot()

        # Layers currently selected (clicked) in the QGIS Layers panel
        try:
            selected_ids = {l.id() for l in self.iface.layerTreeView().selectedLayers()}
        except Exception:
            selected_ids = set()

        def add_nodes(node, indent=0):
            for child in node.children():
                if isinstance(child, QgsLayerTreeGroup):
                    # Add a non-checkable group header
                    grp_item = QListWidgetItem("  " * indent + "▸ " + child.name())
                    grp_item.setFlags(grp_item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsSelectable)
                    # No Qt.UserRole set — signals this is a group header
                    self.layer_list.addItem(grp_item)
                    add_nodes(child, indent + 1)
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer is None:
                        continue
                    if layer.type() not in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
                        continue
                    item = QListWidgetItem("  " * indent + layer.name())
                    item.setData(Qt.UserRole, layer.id())
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    # Pre-check selected layers; fall back to visibility if nothing selected
                    if selected_ids:
                        checked = layer.id() in selected_ids
                    else:
                        checked = child.isVisible()
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self.layer_list.addItem(item)

        add_nodes(root)

    def _select_all(self):
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.data(Qt.UserRole) is not None:
                item.setCheckState(Qt.Checked)

    def _deselect_all(self):
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.data(Qt.UserRole) is not None:
                item.setCheckState(Qt.Unchecked)

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

    # ── Export ───────────────────────────────────────────────────────────────

    def _export(self):
        output_path = self.path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "No output file", "Please select an output file path.")
            return

        selected_ids = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.data(Qt.UserRole) is not None and item.checkState() == Qt.Checked:
                selected_ids.append(item.data(Qt.UserRole))

        if not selected_ids:
            QMessageBox.warning(self, "No layers", "Please select at least one layer to export.")
            return

        # Build layer list and tree structure by traversing the QGIS layer tree
        selected_id_set = {lid for lid in selected_ids if lid}
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
            exporter = WebMapExporter(
                layers=layers,
                output_path=output_path,
                include_layer_control=self.layer_control_cb.isChecked(),
                progress_callback=lambda v: self.progress.setValue(v),
                layer_tree=tree_nodes,
                initial_extent=self._initial_extent,
                scenes=self._scenes,
            )
            exporter.export()
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
