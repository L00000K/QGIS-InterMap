"""Layers tab: layer tree, required layers, QGIS theme application."""
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QCheckBox, QGroupBox, QWidget, QTreeWidget, QTreeWidgetItem,
    QComboBox,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.core import (
    QgsProject, QgsLayerTreeGroup, QgsLayerTreeLayer,
)
from .constants import _PURPLE
from ..compat import LAYER_TYPE_RASTER, LAYER_TYPE_VECTOR


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

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_layers_btn = QPushButton("↻  Refresh from QGIS")
        refresh_layers_btn.setToolTip(
            "Rebuild this list from the current QGIS project.\n"
            "It also updates automatically when layers are added, removed or renamed."
        )
        refresh_layers_btn.clicked.connect(self._refresh_layers_preserving_selection)
        refresh_row.addWidget(refresh_layers_btn)
        layers_layout.addLayout(refresh_row)

        # Basemap option (directly under layer list)
        self.basemap_cb = QCheckBox("Add OpenStreetMap basemap")
        self.basemap_cb.setChecked(False)
        layers_layout.addWidget(self.basemap_cb)

        self.basemap_greyscale_cb = QCheckBox("↳ Render basemap in greyscale")
        self.basemap_greyscale_cb.setChecked(False)
        self.basemap_greyscale_cb.setToolTip(
            "Desaturate the basemap so data layers read more clearly.\n"
            "Viewers can still toggle this from the layers panel."
        )
        self.basemap_greyscale_cb.setEnabled(self.basemap_cb.isChecked())
        self.basemap_cb.toggled.connect(self.basemap_greyscale_cb.setEnabled)
        layers_layout.addWidget(self.basemap_greyscale_cb)

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
            layer_id = item.data(0, Qt.ItemDataRole.UserRole)
            if layer_id is not None:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer and layer.name() in required:
                    item.setCheckState(0, Qt.CheckState.Checked)
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
                    item.setCheckState(0, Qt.CheckState.Checked)
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
        if state == Qt.CheckState.Unchecked:
            layer_id = item.data(0, Qt.ItemDataRole.UserRole)
            if layer_id:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer and layer.name() in self._get_required_layer_names():
                    item.setCheckState(0, Qt.CheckState.Checked)
                    self.layer_tree_widget.blockSignals(False)
                    return

        if state != Qt.CheckState.PartiallyChecked and item.childCount() > 0:
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
        checked = sum(1 for i in range(total) if item.child(i).checkState(0) == Qt.CheckState.Checked)
        partial = sum(1 for i in range(total) if item.child(i).checkState(0) == Qt.CheckState.PartiallyChecked)
        if checked == total:
            item.setCheckState(0, Qt.CheckState.Checked)
        elif checked == 0 and partial == 0:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)
        grandparent = item.parent()
        if grandparent:
            self._update_parent_check_state(grandparent)

    # ── Keeping the tree in step with QGIS ────────────────────────────────
    # The tree used to be built once when the dialog was constructed, so
    # layers added, removed or renamed in QGIS afterwards never showed up
    # and the only way to resync was to restart QGIS.

    def _connect_project_layer_signals(self):
        """Repopulate the layer tree when the QGIS project changes."""
        # Debounce timer; if it cannot be wired we fall back to refreshing
        # directly, so signal wiring never blocks the dialog from opening.
        self._layer_refresh_timer = None
        try:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(200)  # coalesce bulk add/remove
            timer.timeout.connect(self._refresh_layers_preserving_selection)
            self._layer_refresh_timer = timer
        except Exception:
            pass

        proj = QgsProject.instance()
        for signal_name in ("layersAdded", "layersRemoved", "cleared"):
            sig = getattr(proj, signal_name, None)
            if sig is None:
                continue
            try:
                sig.connect(self._schedule_layer_refresh)
            except Exception:
                pass
        root = proj.layerTreeRoot()
        for signal_name in ("addedChildren", "removedChildren"):
            sig = getattr(root, signal_name, None)
            if sig is None:
                continue
            try:
                sig.connect(self._schedule_layer_refresh)
            except Exception:
                pass
        self._hook_layer_name_signals()

    def _hook_layer_name_signals(self):
        """(Re)connect nameChanged on every layer so renames are picked up."""
        for layer in QgsProject.instance().mapLayers().values():
            try:
                layer.nameChanged.disconnect(self._schedule_layer_refresh)
            except Exception:
                pass
            try:
                layer.nameChanged.connect(self._schedule_layer_refresh)
            except Exception:
                pass

    def _schedule_layer_refresh(self, *_args):
        """Debounced entry point — signals may fire many times in a burst."""
        timer = getattr(self, "_layer_refresh_timer", None)
        if timer is None:
            try:
                self._refresh_layers_preserving_selection()
            except Exception:
                pass
            return
        try:
            timer.start()
        except RuntimeError:
            pass  # dialog already destroyed (plugin unloaded)

    def _refresh_layers_preserving_selection(self):
        """Rebuild the tree from the project, keeping the user's ticks."""
        try:
            had_items = self.layer_tree_widget.topLevelItemCount() > 0
        except RuntimeError:
            return  # underlying widget is gone
        keep = self._checked_layer_ids()
        self._populate_layers()
        if had_items:
            self._set_checked_layer_ids(keep)
        self._hook_layer_name_signals()

    def _checked_layer_ids(self):
        ids = set()

        def walk(parent):
            for i in range(parent.childCount()):
                it = parent.child(i)
                lid = it.data(0, Qt.ItemDataRole.UserRole)
                if lid and it.checkState(0) == Qt.CheckState.Checked:
                    ids.add(lid)
                walk(it)

        walk(self.layer_tree_widget.invisibleRootItem())
        return ids

    def _set_checked_layer_ids(self, ids):
        self.layer_tree_widget.blockSignals(True)

        def walk(parent):
            for i in range(parent.childCount()):
                it = parent.child(i)
                lid = it.data(0, Qt.ItemDataRole.UserRole)
                if lid:
                    it.setCheckState(0, Qt.CheckState.Checked if lid in ids else Qt.CheckState.Unchecked)
                walk(it)

        def sync_groups(parent):
            for i in range(parent.childCount()):
                it = parent.child(i)
                sync_groups(it)
                if it.childCount():
                    self._update_parent_check_state(it)

        root_item = self.layer_tree_widget.invisibleRootItem()
        walk(root_item)
        sync_groups(root_item)
        self.layer_tree_widget.blockSignals(False)
        self._update_required_layers()

    def _populate_layers(self):
        self.layer_tree_widget.blockSignals(True)
        self.layer_tree_widget.clear()
        root = QgsProject.instance().layerTreeRoot()

        def add_nodes(parent, node):
            for child in node.children():
                if isinstance(child, QgsLayerTreeGroup):
                    grp = QTreeWidgetItem(parent)
                    grp.setText(0, child.name())
                    grp.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    grp.setCheckState(0, Qt.CheckState.Unchecked)
                    add_nodes(grp, child)
                    self._update_parent_check_state(grp)
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer is None:
                        continue
                    if layer.type() not in (LAYER_TYPE_VECTOR, LAYER_TYPE_RASTER):
                        continue
                    item = QTreeWidgetItem(parent)
                    item.setText(0, layer.name())
                    item.setData(0, Qt.ItemDataRole.UserRole, layer.id())
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                    item.setCheckState(0, Qt.CheckState.Checked if child.isVisible() else Qt.CheckState.Unchecked)

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
            if layer.type() == LAYER_TYPE_RASTER:
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
            layer_id = item.data(0, Qt.ItemDataRole.UserRole)
            if layer_id is not None:
                item.setCheckState(0, Qt.CheckState.Checked if layer_id in visible_ids else Qt.CheckState.Unchecked)
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
        self._set_children_check_state(self.layer_tree_widget.invisibleRootItem(), Qt.CheckState.Checked)
        self.layer_tree_widget.blockSignals(False)

    def _deselect_all(self):
        self.layer_tree_widget.blockSignals(True)
        self._set_children_check_state(self.layer_tree_widget.invisibleRootItem(), Qt.CheckState.Unchecked)
        self.layer_tree_widget.blockSignals(False)

    def _checked_layer_names(self):
        names = []

        def walk(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                layer_id = item.data(0, Qt.ItemDataRole.UserRole)
                if layer_id is not None:
                    if item.checkState(0) == Qt.CheckState.Checked:
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
                layer_id = item.data(0, Qt.ItemDataRole.UserRole)
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
                layer_id = item.data(0, Qt.ItemDataRole.UserRole)
                if layer_id is not None:
                    layer = QgsProject.instance().mapLayer(layer_id)
                    checked = layer is not None and layer.name() in nameset
                    item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
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
                    child_has = child.checkState(0) == Qt.CheckState.Checked
                has_checked = has_checked or child_has
            if item is not root and item.childCount() > 0:
                total = item.childCount()
                n_checked = sum(1 for j in range(total) if item.child(j).checkState(0) == Qt.CheckState.Checked)
                n_partial = sum(1 for j in range(total) if item.child(j).checkState(0) == Qt.CheckState.PartiallyChecked)
                if n_checked == total:
                    item.setCheckState(0, Qt.CheckState.Checked)
                elif n_checked == 0 and n_partial == 0:
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                item.setExpanded(has_checked)
            return has_checked

        walk(root)
        sync_groups(root)
        self.layer_tree_widget.blockSignals(False)
