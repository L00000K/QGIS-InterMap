"""Map Views tab: named views with extents, layer sets, QGIS theme/layout links."""
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QLineEdit, QMessageBox, QGroupBox, QTextEdit, QWidget, QComboBox,
    QInputDialog, QScrollArea, QAbstractItemView,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsPointXY, QgsWkbTypes,
)
from .constants import _PURPLE
from .widgets import _VResizeHandle, _RectExtentTool


class MapViewsTabMixin:
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
        mv_layers_copy_btn = QPushButton("copy from other map view")
        mv_layers_copy_btn.setToolTip("Copy the layer set from another map view in this list")
        mv_layers_copy_btn.clicked.connect(self._mv_copy_layers_from_view)
        layers_panel_vl.addWidget(mv_layers_copy_btn)
        mv_layers_show_btn = QPushButton("🗺  show in canvas")
        mv_layers_show_btn.setToolTip(
            "Apply this view's layer set to the QGIS canvas so you can see what it captures"
        )
        mv_layers_show_btn.clicked.connect(self._mv_show_layers_in_canvas)
        layers_panel_vl.addWidget(mv_layers_show_btn)
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
        mv_ext_copy_btn = QPushButton("copy from other map view")
        mv_ext_copy_btn.setToolTip("Copy the extent from another map view in this list")
        mv_ext_copy_btn.clicked.connect(self._mv_copy_extent_from_view)
        extent_panel_vl.addWidget(mv_ext_copy_btn)
        mv_ext_show_btn = QPushButton("🗺  show in canvas")
        mv_ext_show_btn.setToolTip("Zoom the QGIS canvas to this view's extent")
        mv_ext_show_btn.clicked.connect(self._mv_view_in_canvas)
        extent_panel_vl.addWidget(mv_ext_show_btn)
        self.mv_extent_panel.setVisible(False)
        box_vl.addWidget(self.mv_extent_panel)
        # Absorb spare height at the bottom, so collapsing the layers/extent
        # panels does not spread the name and description boxes down the box.
        box_vl.addStretch()

        # Natural height, not stretch 1: the box should size to its contents
        # and let the scroll area deal with overflow, rather than growing to
        # fill and dragging its contents apart.
        detail_layout.addWidget(mv_settings_box)

        # Duplicate + Delete at the bottom (outside grey box)
        dup_btn = QPushButton("Duplicate map view")
        dup_btn.clicked.connect(self._map_view_duplicate)
        detail_layout.addWidget(dup_btn)

        del_btn = QPushButton("Delete map view")
        del_btn.setObjectName("deleteBtn")
        del_btn.clicked.connect(self._map_view_delete)
        detail_layout.addWidget(del_btn)
        detail_layout.addStretch()

        self.mv_detail_scroll.setWidget(detail_widget)
        mv_layout.addWidget(self.mv_detail_scroll, 1)
        # With no map view selected the detail pane is hidden and nothing else
        # can grow, which left the list floating in the middle of the tab.
        # This takes the spare height so the list stays put at the top.
        mv_layout.addStretch(0)
        self.mv_detail_scroll.setVisible(False)

        self._map_views_list_refresh()
        self._mv_populate_layer_combo()

        return widget

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

    def _mv_show_layers_in_canvas(self):
        """Apply this map view's layer set to the QGIS canvas."""
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return
        mv = self._map_views[idx]
        root = QgsProject.instance().layerTreeRoot()

        theme = mv.get("theme")
        if theme:
            try:
                model = self.iface.layerTreeView().layerTreeModel()
                QgsProject.instance().mapThemeCollection().applyTheme(theme, root, model)
                self.iface.mapCanvas().refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            return

        names = mv.get("layerIds")
        if not names:
            QMessageBox.information(
                self, "No layers",
                "This map view has no layer set yet. Use 'from canvas', 'from theme',\n"
                "'from layout' or 'copy from other map view' to give it one."
            )
            return

        wanted = set(names)
        missing = set(wanted)
        try:
            for node in root.findLayers():
                layer = node.layer()
                if layer is None:
                    continue
                on = layer.name() in wanted
                missing.discard(layer.name())
                # setItemVisibilityChecked is the modern API; fall back for older QGIS.
                try:
                    node.setItemVisibilityChecked(on)
                except AttributeError:
                    node.setVisible(Qt.Checked if on else Qt.Unchecked)
            self.iface.mapCanvas().refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        if missing:
            self.iface.messageBar().pushInfo(
                "InterMap",
                "Applied '%s'. Not in this project: %s" % (
                    mv.get("name", "map view"), ", ".join(sorted(missing)))
            )

    def _mv_pick_other_view(self, title, label):
        """Ask the user to choose a different map view. Returns its index or None."""
        idx = self._editing_map_view_idx
        if idx is None or idx < 0 or idx >= len(self._map_views):
            QMessageBox.information(self, "No map view", "Select a map view first.")
            return None
        others = [(i, mv) for i, mv in enumerate(self._map_views) if i != idx]
        if not others:
            QMessageBox.information(
                self, "No other map views",
                "There is only one map view. Add another before copying between them."
            )
            return None
        names = ["%d. %s" % (i + 1, mv.get("name") or "(unnamed)") for i, mv in others]
        choice, ok = QInputDialog.getItem(self, title, label, names, 0, False)
        if not ok or not choice:
            return None
        return others[names.index(choice)][0]

    def _mv_copy_extent_from_view(self):
        src = self._mv_pick_other_view("Copy extent", "Copy the extent from:")
        if src is None:
            return
        idx = self._editing_map_view_idx
        ext = self._map_views[src].get("extent")
        if not ext:
            QMessageBox.information(
                self, "No extent",
                "'%s' has no extent set." % (self._map_views[src].get("name") or "That view")
            )
            return
        # Copy the values, not the list object, so the two views stay independent.
        ext = [list(ext[0]), list(ext[1])]
        self._map_views[idx]["extent"] = ext
        self._editing_map_view_extent = ext
        self._update_mv_extent_label(ext)
        self._mv_update_rubber_bands()
        self._mark_unsaved()

    def _mv_copy_layers_from_view(self):
        src = self._mv_pick_other_view("Copy layers", "Copy the layer set from:")
        if src is None:
            return
        idx = self._editing_map_view_idx
        smv, dmv = self._map_views[src], self._map_views[idx]
        # A view's layers are defined by exactly one of theme / layout / layerIds,
        # so clear all three before copying whichever the source uses.
        for key in ("theme", "layout", "layerIds"):
            dmv.pop(key, None)
        if smv.get("theme"):
            dmv["theme"] = smv["theme"]
            self._update_mv_layers_label(None, theme=dmv["theme"])
        elif smv.get("layout"):
            import copy as _copy
            dmv["layout"] = _copy.deepcopy(smv["layout"])
            dmv["layerIds"] = list(smv.get("layerIds") or [])
            self._update_mv_layers_label(dmv.get("layerIds"), layout=dmv["layout"])
        elif smv.get("layerIds"):
            dmv["layerIds"] = list(smv["layerIds"])
            self._update_mv_layers_label(dmv["layerIds"])
        else:
            QMessageBox.information(
                self, "No layers",
                "'%s' has no layer set to copy." % (smv.get("name") or "That view")
            )
            return
        self._update_required_layers()
        self._mark_unsaved()

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
                    rb.setStrokeColor(QColor(_PURPLE))
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
        self._update_mv_layers_label(mv.get("layerIds"), mv.get("theme"), mv.get("layout"))
        self._mv_update_rubber_bands()

    def _update_mv_extent_label(self, ext):
        if ext:
            self.map_view_extent_label.setText(
                f"View extent: <b>S {ext[0][0]:.4f}  W {ext[0][1]:.4f}  "
                f"N {ext[1][0]:.4f}  E {ext[1][1]:.4f}</b>"
            )
        else:
            self.map_view_extent_label.setText("View extent: <b>(not set)</b>")

    def _update_mv_layers_label(self, layer_ids, theme=None, layout=None):
        import html as _h
        lyt = f"layout: <b>{_h.escape(layout)}</b> → " if layout else ""
        if theme:
            self.map_view_layers_label.setText(
                f"Layers: {lyt}theme: <b>{_h.escape(theme)}</b>"
                if layout else
                f"Layers: <b>theme: {_h.escape(theme)}</b>"
            )
        elif layer_ids:
            n = len(layer_ids)
            if layout:
                self.map_view_layers_label.setText(
                    f"Layers: layout: <b>{_h.escape(layout)}</b> → <b>{n} layer(s)</b>"
                )
            else:
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
        self._map_views[idx].pop("layout", None)
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
        self._map_views[idx].pop("layout", None)
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

    def _pick_layout(self):
        """Prompt user to pick a print layout and map frame.
        Returns (QgsPrintLayout, QgsLayoutItemMap, name) or (None, None, None)."""
        try:
            from qgis.core import QgsLayoutItemMap
            lm = QgsProject.instance().layoutManager()
            layouts = [l for l in lm.layouts() if hasattr(l, "referenceMap")]
        except Exception:
            layouts = []
        if not layouts:
            QMessageBox.information(self, "No layouts", "No print layouts found in this project.")
            return None, None, None
        names = [l.name() for l in layouts]
        name, ok = QInputDialog.getItem(self, "Select layout", "Print layout:", names, 0, False)
        if not ok or not name:
            return None, None, None
        layout = next((l for l in layouts if l.name() == name), None)
        if layout is None:
            return None, None, None

        try:
            map_items = [item for item in layout.items()
                         if isinstance(item, QgsLayoutItemMap)]
        except Exception:
            map_items = []

        if not map_items:
            QMessageBox.warning(self, "No map frames",
                                f"Layout '{name}' has no map frames.")
            return None, None, None

        if len(map_items) == 1:
            return layout, map_items[0], name

        # Multiple map frames — let the user pick
        frame_labels = []
        for i, item in enumerate(map_items):
            label = item.id() or f"Map {i + 1}"
            ref_marker = " (reference)" if item == layout.referenceMap() else ""
            frame_labels.append(f"{label}{ref_marker}")
        frame_choice, ok2 = QInputDialog.getItem(
            self, "Select map frame", "Map frame:", frame_labels, 0, False
        )
        if not ok2:
            return None, None, None
        chosen_idx = frame_labels.index(frame_choice)
        return layout, map_items[chosen_idx], name

    def _extent_from_layout(self, map_item):
        """Return [[s,w],[n,e]] geographic extent from a QgsLayoutItemMap, or None."""
        try:
            rect = map_item.extent()
            map_crs = map_item.crs() if map_item.crs().isValid() else QgsProject.instance().crs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(map_crs, wgs84, QgsProject.instance())
            e = tr.transformBoundingBox(rect)
            return [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
        except Exception:
            return None

    def _layers_from_layout(self, layout, map_item):
        """Return list of layer names from a QgsLayoutItemMap, or None if following project.
        Also detects map themes and stores theme info on the result dict."""
        try:
            # Check for a map theme override
            theme = map_item.followVisibilityPresetName() if map_item.followVisibilityPreset() else None
            layers = map_item.layers()
            if layers:
                layer_names = [l.name() for l in layers if l is not None]
                return {"mode": "layers", "theme": theme, "layerIds": layer_names}
            if theme:
                # Follows a theme but no explicit layer list — resolve from theme
                try:
                    theme_rec = QgsProject.instance().mapThemeCollection().mapThemeState(theme)
                    theme_layers = [l.name() for l in theme_rec.layerRecords()
                                    if l is not None] if theme_rec else []
                    return {"mode": "theme", "theme": theme, "layerIds": theme_layers}
                except Exception:
                    return {"mode": "theme", "theme": theme, "layerIds": []}
        except Exception:
            pass
        return None

    def _map_view_add_from_layout(self):
        layout, map_item, name = self._pick_layout()
        if layout is None:
            return
        ext = self._extent_from_layout(map_item)
        layers_info = self._layers_from_layout(layout, map_item)
        if layers_info and layers_info.get("theme"):
            from qgis.PyQt.QtWidgets import QMessageBox as _QMB
            theme_name = layers_info["theme"]
            _QMB.information(
                self, "Map theme detected",
                f"This map frame uses the theme \"{theme_name}\".\n"
                "Layer visibility will reflect that theme in the web map."
            )
        layer_names = (layers_info or {}).get("layerIds") or []
        theme = (layers_info or {}).get("theme")
        mv = {"name": name, "notes": "", "extent": ext, "layerIds": layer_names, "layout": name}
        if theme:
            mv["theme"] = theme
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
        layout, map_item, _name = self._pick_layout()
        if layout is None:
            return
        ext = self._extent_from_layout(map_item)
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
        layout, map_item, layout_name = self._pick_layout()
        if layout is None:
            return
        layers_info = self._layers_from_layout(layout, map_item)
        if layers_info is None:
            QMessageBox.information(
                self, "No layer override",
                "This layout's map item follows the project's layer visibility.\n"
                "Use 'from canvas' to snapshot the current canvas layers instead."
            )
            return
        layer_names = layers_info.get("layerIds") or []
        theme = layers_info.get("theme")
        if theme:
            from qgis.PyQt.QtWidgets import QMessageBox as _QMB
            _QMB.information(
                self, "Map theme detected",
                f"This map frame uses the theme \"{theme}\".\n"
                "Layer visibility will reflect that theme in the web map."
            )
        self._map_views[idx]["layerIds"] = layer_names
        self._map_views[idx]["layout"] = layout_name
        if theme:
            self._map_views[idx]["theme"] = theme
        else:
            self._map_views[idx].pop("theme", None)
        self._update_mv_layers_label(layer_names, theme=theme, layout=layout_name)
        self._update_required_layers()

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
