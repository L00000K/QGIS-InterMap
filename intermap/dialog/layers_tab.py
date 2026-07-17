"""Layers tab: layer tree, required layers, QGIS theme application."""
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QCheckBox, QGroupBox, QWidget, QTreeWidget, QTreeWidgetItem,
    QComboBox,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer,
)
from .constants import _PURPLE


class LayersTabMixin:
    def _build_layers_tab(self):
        widget = QWidget()
        layers_layout = QVBoxLayout(widget)

        # Sub-header
        req_lbl = QLabel("Layers selected in map views are required and cannot be deselected.")
        req_lbl.setWordWrap(True)
        req_lbl.setStyleSheet(
            f"color: {_PURPLE}; font-size: 10px; font-weight: 600; padding: 2px 0 4px 0;"
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
                    item.setForeground(0, QColor(_PURPLE))
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
                    item.setForeground(0, QColor(_PURPLE))
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
        self._populate_elevation_raster_combo()
        self._mv_populate_layer_combo()
        self._update_required_layers()

    def _populate_elevation_raster_combo(self):
        """Populate elevation raster combo with available raster layers."""
        self.elevation_raster_combo.blockSignals(True)
        current_data = self.elevation_raster_combo.currentData()
        self.elevation_raster_combo.clear()
        self.elevation_raster_combo.addItem("(none)", None)
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.RasterLayer:
                self.elevation_raster_combo.addItem(layer.name(), layer.id())
        # Restore previous selection if it still exists
        if current_data:
            idx = self.elevation_raster_combo.findData(current_data)
            if idx >= 0:
                self.elevation_raster_combo.setCurrentIndex(idx)
        self.elevation_raster_combo.blockSignals(False)

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
