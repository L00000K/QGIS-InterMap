"""Lite mode: simplified single-tab export flow."""
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QLineEdit, QMessageBox, QGroupBox, QFormLayout,
    QWidget, QComboBox,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.core import (
    QgsProject, QgsMapLayer, QgsLayerTreeGroup, QgsLayerTreeLayer,
    QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsRectangle, QgsPointXY, QgsWkbTypes,
)
from .constants import _PURPLE


class LiteModeMixin:
    def _build_lite_layers_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        name_form = QFormLayout()
        self.lite_map_name_edit = QLineEdit()
        self.lite_map_name_edit.setPlaceholderText("My web map")
        name_form.addRow("Map name:", self.lite_map_name_edit)
        layout.addLayout(name_form)

        extent_group = QGroupBox("Initial map extent")
        extent_vl = QVBoxLayout(extent_group)
        self.lite_extent_label = QLabel("(not set — will use current canvas on export)")
        self.lite_extent_label.setStyleSheet("color: #666; font-size: 10px;")
        self.lite_extent_label.setWordWrap(True)
        extent_vl.addWidget(self.lite_extent_label)
        extent_btn_row = QHBoxLayout()
        _canvas_ext_btn = QPushButton("From current canvas")
        _canvas_ext_btn.clicked.connect(self._lite_extent_from_canvas)
        _draw_ext_btn = QPushButton("Draw on canvas")
        _draw_ext_btn.clicked.connect(self._lite_extent_draw)
        extent_btn_row.addWidget(_canvas_ext_btn)
        extent_btn_row.addWidget(_draw_ext_btn)
        extent_vl.addLayout(extent_btn_row)
        layout.addWidget(extent_group)

        layers_group = QGroupBox("Layers")
        layers_vl = QVBoxLayout(layers_group)

        mode_row = QHBoxLayout()
        _copy_btn = QPushButton("Copy from canvas")
        _copy_btn.setToolTip("Populate list from current canvas layer visibility")
        _copy_btn.clicked.connect(self._lite_copy_from_canvas)
        mode_row.addWidget(_copy_btn)
        self.lite_theme_btn = QPushButton("Set to theme")
        self.lite_theme_btn.setCheckable(True)
        self.lite_theme_btn.setToolTip("Apply a QGIS map theme (layer checkboxes will be greyed out)")
        self.lite_theme_btn.toggled.connect(self._lite_toggle_theme_mode)
        mode_row.addWidget(self.lite_theme_btn)
        mode_row.addStretch()
        layers_vl.addLayout(mode_row)

        self.lite_theme_combo = QComboBox()
        self.lite_theme_combo.setVisible(False)
        self.lite_theme_combo.currentIndexChanged.connect(self._lite_apply_theme)
        layers_vl.addWidget(self.lite_theme_combo)

        self.lite_layers_list = QListWidget()
        self.lite_layers_list.setMinimumHeight(160)
        layers_vl.addWidget(self.lite_layers_list)

        layout.addWidget(layers_group)
        layout.addStretch()
        return widget

    def _lite_extent_from_canvas(self):
        self._lite_extent = self._capture_canvas_extent()
        self._lite_update_extent_label()

    def _lite_extent_draw(self):
        canvas = self.iface.mapCanvas()
        def _on_rect(rect):
            try:
                project_crs = QgsProject.instance().crs()
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                tr = QgsCoordinateTransform(project_crs, wgs84, QgsProject.instance())
                e = tr.transformBoundingBox(rect)
                self._lite_extent = [[e.yMinimum(), e.xMinimum()], [e.yMaximum(), e.xMaximum()]]
                self._lite_update_extent_label()
            except Exception:
                pass
        try:
            from qgis.gui import QgsMapTool, QgsRubberBand
            class _DrawTool(QgsMapTool):
                rectDrawn = pyqtSignal(object)
                def __init__(self, canvas):
                    super().__init__(canvas)
                    self._start = None
                    self._rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
                    self._rb.setColor(QColor(_PURPLE))
                    self._rb.setWidth(2)
                def canvasPressEvent(self, e):
                    self._start = self.toMapCoordinates(e.pos())
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
            prev = canvas.mapTool()
            tool = _DrawTool(canvas)
            def _done(rect):
                _on_rect(rect)
                canvas.setMapTool(prev)
            tool.rectDrawn.connect(_done)
            canvas.setMapTool(tool)
        except Exception:
            pass

    def _lite_update_extent_label(self):
        ext = self._lite_extent
        if ext:
            [[s, w], [n, e]] = ext
            self.lite_extent_label.setText(
                f"N {n:.4f}  S {s:.4f}  W {w:.4f}  E {e:.4f}"
            )
        else:
            self.lite_extent_label.setText("(not set — will use current canvas on export)")

    def _lite_populate_layers(self):
        self.lite_layers_list.blockSignals(True)
        self.lite_layers_list.clear()
        root = QgsProject.instance().layerTreeRoot()
        def _add(node):
            for child in node.children():
                if isinstance(child, QgsLayerTreeGroup):
                    _add(child)
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer is None:
                        continue
                    if layer.type() not in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
                        continue
                    item = QListWidgetItem(layer.name())
                    item.setData(Qt.UserRole, layer.id())
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    item.setCheckState(Qt.Checked if child.isVisible() else Qt.Unchecked)
                    self.lite_layers_list.addItem(item)
        _add(root)
        self.lite_layers_list.blockSignals(False)
        self.lite_theme_combo.blockSignals(True)
        self.lite_theme_combo.clear()
        self.lite_theme_combo.addItem("— Select theme —", "")
        try:
            for name in QgsProject.instance().mapThemeCollection().mapThemes():
                self.lite_theme_combo.addItem(name, name)
        except Exception:
            pass
        self.lite_theme_combo.blockSignals(False)

    def _lite_copy_from_canvas(self):
        self._lite_populate_layers()

    def _lite_toggle_theme_mode(self, checked):
        self.lite_theme_combo.setVisible(checked)
        self.lite_layers_list.setEnabled(not checked)
        if checked and self.lite_theme_combo.currentData():
            self._lite_apply_theme(self.lite_theme_combo.currentIndex())

    def _lite_apply_theme(self, index):
        if not self.lite_theme_btn.isChecked():
            return
        theme_name = self.lite_theme_combo.itemData(index)
        if not theme_name:
            return
        try:
            visible_ids = {
                l.id() for l in
                QgsProject.instance().mapThemeCollection().mapThemeVisibleLayers(theme_name)
            }
        except Exception:
            return
        self.lite_layers_list.blockSignals(True)
        for i in range(self.lite_layers_list.count()):
            item = self.lite_layers_list.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in visible_ids else Qt.Unchecked)
        self.lite_layers_list.blockSignals(False)

    def _export_lite(self, output_path):
        selected_ids = [
            self.lite_layers_list.item(i).data(Qt.UserRole)
            for i in range(self.lite_layers_list.count())
            if self.lite_layers_list.item(i).checkState() == Qt.Checked
        ]
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

        map_name = self.lite_map_name_edit.text().strip() or QgsProject.instance().baseName() or "Web Map"
        extent = self._lite_extent or self._capture_canvas_extent()

        self.export_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(layers) + 1)
        self.progress.setValue(0)
        try:
            from ..exporter import WebMapExporter
            info_panel = {
                "enabled": True,
                "title": map_name,
                "text": "",
                "doc_number": "", "revision": "", "purpose": "",
                "client": "", "client_img": "", "project_number": "",
                "project": "", "project_img": "",
                "include_doc_control": False,
                "include_project_info": False,
                "include_doc_metadata": False,
                "created_by": "", "date": "",
                "originated_name": "", "originated_date": "",
                "checked_name": "", "checked_date": "",
                "reviewed_name": "", "reviewed_date": "",
                "approved_name": "", "approved_date": "",
            }
            exporter = WebMapExporter(
                layers=layers,
                output_path=output_path,
                include_layer_control=True,
                include_basemap=self.basemap_cb.isChecked(),
                progress_callback=lambda v: self.progress.setValue(v),
                layer_tree=tree_nodes,
                initial_extent=extent,
                map_views=[],
                info_panel=info_panel,
                theme=self.export_theme_combo.currentData(),
                feat_identify=True,
                feat_attr_table=True,
                feat_attr_csv=True,
                feat_attr_geojson=True,
                feat_measure=True,
                feat_filter=True,
                feat_search=True,
                feat_minimap=True,
                feat_fancy_labels=True,
                feat_changelog=False,
                changelog=[],
                feat_3d_elevation_raster=self.elevation_raster_combo.currentData(),
                report_md_path=self.report_md_edit.text().strip(),
                report_figures_dir=self.report_figures_edit.text().strip(),
                cog_proxy=self.cog_proxy_edit.text().strip(),
            )
            exporter.export()
            self._show_success(output_path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            self.export_btn.setEnabled(True)
            self.progress.setVisible(False)
