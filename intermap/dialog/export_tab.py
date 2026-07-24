"""Export tab: output/report paths, feature toggles, the export run itself."""
import os
import datetime
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLineEdit,
    QMessageBox, QCheckBox, QGroupBox, QFormLayout, QWidget, QLabel,
    QComboBox, QDoubleSpinBox, QTreeWidget,
)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.core import QgsProject, QgsLayerTreeGroup, QgsLayerTreeLayer


class ExportTabMixin:
    def _build_setup_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ── Map profile: capabilities that reveal their own tabs ──────────
        cap_group = QGroupBox("Map profile — switch on what this map needs")
        cap_group.setObjectName("greyBox")
        cap_vl = QVBoxLayout(cap_group)
        cap_vl.setSpacing(5)
        self.cap_title_cb = QCheckBox("Title block  ·  client, project no., document control & revisions")
        self.cap_views_cb = QCheckBox("Map views  ·  named preset extents & layer sets")
        self.cap_report_cb = QCheckBox("Report  ·  scrolling story panel (Markdown or PDF)")
        self.feat_3d_cb = QCheckBox("3D view  ·  Cesium globe, extrusion & terrain")
        self.feat_3d_cb.setChecked(False)
        for _cb in (self.cap_title_cb, self.cap_views_cb, self.cap_report_cb, self.feat_3d_cb):
            _cb.toggled.connect(self._update_capability_tabs)
            _cb.toggled.connect(self._mark_unsaved)
            cap_vl.addWidget(_cb)
        _simple_lbl = QLabel("Leave everything off for a simple single-page map.")
        _simple_lbl.setStyleSheet("color:#6B7280; font-size:10px; padding-left:2px;")
        cap_vl.addWidget(_simple_lbl)
        layout.addWidget(cap_group)

        theme_group = QGroupBox("Export colour theme")
        theme_form = QFormLayout(theme_group)
        self.export_theme_combo = QComboBox()
        self.export_theme_combo.addItem("Grey / Black", "corporate")
        self.export_theme_combo.addItem("Blue", "purple")
        self.export_theme_combo.addItem("Dark", "dark")
        self.export_theme_combo.setToolTip("Colour theme applied to the exported web map")
        theme_form.addRow("Theme:", self.export_theme_combo)
        layout.addWidget(theme_group)

        tools_group = QGroupBox("Interactive tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(4)

        self.feat_layers_cb = QCheckBox("Layers panel")
        self.feat_layers_cb.setChecked(True)
        tools_layout.addWidget(self.feat_layers_cb)
        # alias kept for legacy _export reference
        self.layer_control_cb = self.feat_layers_cb

        self.feat_identify_cb = QCheckBox("Identify features")
        self.feat_identify_cb.setChecked(True)
        tools_layout.addWidget(self.feat_identify_cb)

        self.feat_attr_table_cb = QCheckBox("Attribute table")
        self.feat_attr_table_cb.setChecked(True)
        tools_layout.addWidget(self.feat_attr_table_cb)

        _sub = QWidget()
        _sub_vl = QVBoxLayout(_sub)
        _sub_vl.setContentsMargins(20, 0, 0, 0)
        _sub_vl.setSpacing(2)
        self.feat_attr_csv_cb = QCheckBox("↳ Export CSV")
        self.feat_attr_csv_cb.setChecked(True)
        _sub_vl.addWidget(self.feat_attr_csv_cb)
        self.feat_attr_geojson_cb = QCheckBox("↳ Export GeoJSON")
        self.feat_attr_geojson_cb.setChecked(True)
        _sub_vl.addWidget(self.feat_attr_geojson_cb)
        tools_layout.addWidget(_sub)

        self.feat_measure_cb = QCheckBox("Measure tool")
        self.feat_measure_cb.setChecked(True)
        tools_layout.addWidget(self.feat_measure_cb)

        self.feat_filter_cb = QCheckBox("Filter toolbar + layer filters")
        self.feat_filter_cb.setChecked(True)
        tools_layout.addWidget(self.feat_filter_cb)

        self.feat_search_cb = QCheckBox("Smart search")
        self.feat_search_cb.setChecked(True)
        tools_layout.addWidget(self.feat_search_cb)

        self.feat_minimap_cb = QCheckBox("Minimap")
        self.feat_minimap_cb.setChecked(True)
        tools_layout.addWidget(self.feat_minimap_cb)

        self.feat_fancy_labels_cb = QCheckBox("Label & symbology controls (cluster, spread…)")
        self.feat_fancy_labels_cb.setChecked(True)
        tools_layout.addWidget(self.feat_fancy_labels_cb)

        self.feat_changelog_cb = QCheckBox("Changelog (collapsible panel under map views)")
        self.feat_changelog_cb.setChecked(True)
        tools_layout.addWidget(self.feat_changelog_cb)

        self.feat_sketch_cb = QCheckBox("Sketching / annotation tools")
        self.feat_sketch_cb.setChecked(False)
        tools_layout.addWidget(self.feat_sketch_cb)

        layout.addWidget(tools_group)

        # ── Remote raster sources (COG on blob storage) ──────────────────
        self.cog_group = QGroupBox("Remote raster sources (optional)")
        cog_form = QFormLayout(self.cog_group)
        cog_form.setContentsMargins(8, 6, 8, 8)
        cog_form.setSpacing(6)
        self.cog_proxy_edit = QLineEdit()
        self.cog_proxy_edit.setPlaceholderText("e.g. https://my-worker.workers.dev/?url={url}")
        self.cog_proxy_edit.setToolTip(
            "Optional CORS proxy for remote Cloud Optimized GeoTIFFs (COGs)\n"
            "whose blob storage does not send CORS headers.\n\n"
            "Put {url} where the (URL-encoded) COG URL should be inserted; if\n"
            "{url} is omitted, the encoded URL is appended to the end.\n\n"
            "The proxy MUST forward HTTP Range requests — public proxies that\n"
            "buffer the whole response will not work for large COGs. A small\n"
            "Cloudflare Worker is the recommended option."
        )
        cog_form.addRow("COG CORS proxy:", self.cog_proxy_edit)
        layout.addWidget(self.cog_group)

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

    def _build_3d_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # ── 3D settings ───────────────────────────────────────────────────
        self.d3_group = QGroupBox("3D view settings")
        d3_group = self.d3_group
        d3_form  = QFormLayout(d3_group)
        d3_form.setContentsMargins(8, 6, 8, 8)
        d3_form.setSpacing(6)

        self.cesium_ion_token_edit = QLineEdit()
        self.cesium_ion_token_edit.setPlaceholderText("Paste Cesium Ion token for terrain + OSM Buildings")
        self.cesium_ion_token_edit.setToolTip(
            "Optional free Cesium Ion access token (cesium.com). "
            "Enables real-world terrain and global 3D building footprints."
        )
        d3_form.addRow("Cesium Ion token:", self.cesium_ion_token_edit)

        self.google_maps_key_edit = QLineEdit()
        self.google_maps_key_edit.setPlaceholderText("Paste Google Maps API key for Photorealistic 3D Tiles")
        self.google_maps_key_edit.setToolTip(
            "Optional Google Maps Platform API key. "
            "Enables Google Photorealistic 3D Tiles (photorealistic buildings + imagery)."
        )
        d3_form.addRow("Google Maps key:", self.google_maps_key_edit)

        extrude_row = QHBoxLayout()
        self.extrude_field_edit = QLineEdit()
        self.extrude_field_edit.setPlaceholderText("e.g. height_m or floor_count")
        self.extrude_field_edit.setToolTip(
            "Optional attribute field name used to extrude polygon layers into 3D. "
            "Leave blank for flat polygons."
        )
        self.extrude_scale_spin = QDoubleSpinBox()
        self.extrude_scale_spin.setRange(0.01, 10000.0)
        self.extrude_scale_spin.setValue(1.0)
        self.extrude_scale_spin.setDecimals(2)
        self.extrude_scale_spin.setSuffix(" m/unit")
        self.extrude_scale_spin.setToolTip("Multiply field value by this to get height in metres")
        extrude_row.addWidget(self.extrude_field_edit)
        extrude_row.addWidget(self.extrude_scale_spin)
        d3_form.addRow("Extrude field:", extrude_row)

        self.elevation_raster_combo = QComboBox()
        self.elevation_raster_combo.addItem("(none)", None)
        self.elevation_raster_combo.setToolTip(
            "Optional raster layer to use as elevation surface for 3D view.\n"
            "Will be converted to a heightmap; features without Z will be draped on this surface."
        )
        d3_form.addRow("Elevation raster:", self.elevation_raster_combo)

        layout.addWidget(d3_group)
        layout.addStretch()
        return widget

    def _build_report_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # ── Report / story mode ───────────────────────────────────────────
        self.report_group = QGroupBox("Report / story mode")
        report_form = QFormLayout(self.report_group)
        report_form.setContentsMargins(8, 6, 8, 8)
        report_form.setSpacing(6)

        report_md_row = QHBoxLayout()
        self.report_md_edit = QLineEdit()
        self.report_md_edit.setPlaceholderText("Select report .md file…")
        self.report_md_edit.setToolTip(
            "Markdown report rendered as a scrolling story panel beside the map.\n\n"
            "Front-matter supports title: and autolink: (layer/field/pattern).\n"
            "Directives:\n"
            "  :::view <Map View name> [3d pitch=-35 heading=120]\n"
            "  ![caption](figures/plan.png){#fig:plan}\n"
            "  {#tbl:results caption=\"...\"} above a markdown table\n"
            "  :::table layer=\"Boreholes\" filter=\"depth > 10\" {#tbl:bh caption=\"...\"}\n"
            "Links: [BH-101](gis:Boreholes?ID=BH-101), [text](view:Name), (fig:plan)"
        )
        report_md_btn = QPushButton("Browse…")
        report_md_btn.clicked.connect(self._browse_report_md)
        report_md_row.addWidget(self.report_md_edit)
        report_md_row.addWidget(report_md_btn)
        report_form.addRow("Report markdown:", report_md_row)

        report_fig_row = QHBoxLayout()
        self.report_figures_edit = QLineEdit()
        self.report_figures_edit.setPlaceholderText("Figures folder (optional — defaults beside the .md)")
        self.report_figures_edit.setToolTip(
            "Folder that image paths in the markdown are resolved against.\n"
            "Images are embedded into the exported HTML."
        )
        report_fig_btn = QPushButton("Browse…")
        report_fig_btn.clicked.connect(self._browse_report_figures)
        report_fig_row.addWidget(self.report_figures_edit)
        report_fig_row.addWidget(report_fig_btn)
        report_form.addRow("Figures folder:", report_fig_row)

        # PDF report (alternative to markdown; takes precedence when set)
        report_pdf_row = QHBoxLayout()
        self.report_pdf_edit = QLineEdit()
        self.report_pdf_edit.setPlaceholderText("…or select a report .pdf")
        self.report_pdf_edit.setToolTip(
            "PDF report shown as a scrolling panel beside the map.\n"
            "Bind pages to Map Views below — as the reader scrolls, the map\n"
            "flies to the view bound to the page in front of them.\n"
            "When both a PDF and a markdown report are set, the PDF wins."
        )
        report_pdf_btn = QPushButton("Browse…")
        report_pdf_btn.clicked.connect(self._browse_report_pdf)
        report_pdf_row.addWidget(self.report_pdf_edit)
        report_pdf_row.addWidget(report_pdf_btn)
        report_form.addRow("Report PDF:", report_pdf_row)

        # Page → view bindings table
        self.pdf_bindings_tree = QTreeWidget()
        self.pdf_bindings_tree.setColumnCount(3)
        self.pdf_bindings_tree.setHeaderLabels(["Page", "Map view", "Options"])
        self.pdf_bindings_tree.setRootIsDecorated(False)
        self.pdf_bindings_tree.setMaximumHeight(110)
        self.pdf_bindings_tree.setToolTip(
            "As the PDF is scrolled, reaching a listed page applies its map view.\n"
            "Options (optional) use the :::view grammar, e.g.:  3d pitch=-35 heading=120")
        pdf_bind_btns = QHBoxLayout()
        pdf_bind_add = QPushButton("+ Add binding")
        pdf_bind_add.clicked.connect(self._pdf_binding_add)
        pdf_bind_del = QPushButton("Remove")
        pdf_bind_del.clicked.connect(self._pdf_binding_remove)
        pdf_bind_btns.addWidget(pdf_bind_add)
        pdf_bind_btns.addWidget(pdf_bind_del)
        pdf_bind_btns.addStretch()
        pdf_bind_col = QVBoxLayout()
        pdf_bind_col.addWidget(self.pdf_bindings_tree)
        pdf_bind_col.addLayout(pdf_bind_btns)
        report_form.addRow("Page bindings:", pdf_bind_col)

        layout.addWidget(self.report_group)
        layout.addStretch()
        return widget

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

    def _browse_report_md(self):
        current = self.report_md_edit.text().strip()
        start_dir = os.path.dirname(current) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select report markdown", start_dir,
            "Markdown (*.md *.markdown *.txt);;All files (*)"
        )
        if path:
            self.report_md_edit.setText(path)
            # Default the figures folder to a 'figures' dir beside the .md
            if not self.report_figures_edit.text().strip():
                guess = os.path.join(os.path.dirname(path), "figures")
                if os.path.isdir(guess):
                    self.report_figures_edit.setText(guess)

    def _browse_report_figures(self):
        current = self.report_figures_edit.text().strip()
        path = QFileDialog.getExistingDirectory(
            self, "Select figures folder", current or ""
        )
        if path:
            self.report_figures_edit.setText(path)

    def _browse_report_pdf(self):
        current = self.report_pdf_edit.text().strip()
        start_dir = os.path.dirname(current) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select report PDF", start_dir,
            "PDF (*.pdf);;All files (*)"
        )
        if path:
            self.report_pdf_edit.setText(path)
            if self.pdf_bindings_tree.topLevelItemCount() == 0:
                self._pdf_binding_add()

    def _pdf_view_names(self):
        return [mv.get("name", "") for mv in getattr(self, "_map_views", [])
                if mv.get("name")]

    def _pdf_binding_add(self, page=1, view="", opts=""):
        from qgis.PyQt.QtWidgets import QTreeWidgetItem, QSpinBox
        item = QTreeWidgetItem(["", "", ""])
        self.pdf_bindings_tree.addTopLevelItem(item)
        spin = QSpinBox()
        spin.setRange(1, 9999)
        spin.setValue(int(page) if page else 1)
        spin.valueChanged.connect(self._mark_unsaved)
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._pdf_view_names())
        if view:
            combo.setCurrentText(view)
        combo.currentTextChanged.connect(self._mark_unsaved)
        opts_edit = QLineEdit(opts or "")
        opts_edit.setPlaceholderText("e.g. 3d pitch=-35")
        opts_edit.textChanged.connect(self._mark_unsaved)
        self.pdf_bindings_tree.setItemWidget(item, 0, spin)
        self.pdf_bindings_tree.setItemWidget(item, 1, combo)
        self.pdf_bindings_tree.setItemWidget(item, 2, opts_edit)
        self._mark_unsaved()

    def _pdf_binding_remove(self):
        tree = self.pdf_bindings_tree
        item = tree.currentItem()
        if item is None and tree.topLevelItemCount():
            item = tree.topLevelItem(tree.topLevelItemCount() - 1)
        if item is not None:
            tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
            self._mark_unsaved()

    def _pdf_bindings_collect(self):
        out = []
        tree = self.pdf_bindings_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            spin = tree.itemWidget(item, 0)
            combo = tree.itemWidget(item, 1)
            opts_edit = tree.itemWidget(item, 2)
            if spin is None or combo is None:
                continue
            view = combo.currentText().strip()
            if view:
                entry = {"page": spin.value(), "view": view}
                opts = opts_edit.text().strip() if opts_edit else ""
                if opts:
                    entry["opts"] = opts
                out.append(entry)
        return out

    def _pdf_bindings_apply(self, bindings):
        self.pdf_bindings_tree.clear()
        for b in bindings or []:
            self._pdf_binding_add(b.get("page", 1), b.get("view", ""),
                                  b.get("opts", ""))

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

        # Warn if any vector layer is likely to produce a slow/large export.
        # Two checks: many features (lots of requests) OR large source file
        # (dense geometry — e.g. flow lines with thousands of vertices per feature).
        def _layer_src_mb(lr):
            try:
                import os
                uri = lr.dataProvider().dataSourceUri().split("|")[0].strip()
                if os.path.isfile(uri):
                    return os.path.getsize(uri) / 1_048_576
            except Exception:
                pass
            return 0.0

        heavy = []
        for lr in layers:
            if not hasattr(lr, "featureCount"):
                continue
            fc   = lr.featureCount()
            mb   = _layer_src_mb(lr)
            if fc > 50_000:
                heavy.append(f"  {lr.name()}  ({fc:,} features)")
            elif mb > 20:
                heavy.append(f"  {lr.name()}  (~{mb:.0f} MB source — dense geometry)")

        if heavy:
            msg = (
                "The following layers are large and may produce a slow or "
                "unresponsive webmap:\n\n"
                + "\n".join(heavy)
                + "\n\nFor line/polygon layers with dense geometry, simplify first:\n"
                "Vector → Geometry Tools → Simplify (tolerance ~0.0001°).\n\n"
                "Continue anyway?"
            )
            if QMessageBox.question(self, "Performance warning", msg,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        self.export_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(layers) + 1)
        self.progress.setValue(0)

        try:
            from ..exporter import WebMapExporter
            info_panel = None
            if self.cap_title_cb.isChecked() and self.include_info_cb.isChecked():
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
                map_views=(self._map_views if self.cap_views_cb.isChecked() else []),
                info_panel=info_panel,
                theme=self.export_theme_combo.currentData(),
                feat_identify=self.feat_identify_cb.isChecked(),
                feat_attr_table=self.feat_attr_table_cb.isChecked(),
                feat_attr_csv=self.feat_attr_csv_cb.isChecked(),
                feat_attr_geojson=self.feat_attr_geojson_cb.isChecked(),
                feat_measure=self.feat_measure_cb.isChecked(),
                feat_filter=self.feat_filter_cb.isChecked(),
                feat_search=self.feat_search_cb.isChecked(),
                feat_minimap=self.feat_minimap_cb.isChecked(),
                feat_fancy_labels=self.feat_fancy_labels_cb.isChecked(),
                feat_changelog=self.feat_changelog_cb.isChecked(),
                changelog=list(self._changelog),
                feat_3d=self.feat_3d_cb.isChecked(),
                feat_sketch=self.feat_sketch_cb.isChecked(),
                cesium_ion_token=self.cesium_ion_token_edit.text().strip(),
                google_maps_key=self.google_maps_key_edit.text().strip(),
                feat_3d_extrude_field=self.extrude_field_edit.text().strip(),
                feat_3d_extrude_scale=self.extrude_scale_spin.value(),
                feat_3d_elevation_raster=self.elevation_raster_combo.currentData(),
                report_md_path=(self.report_md_edit.text().strip() if self.cap_report_cb.isChecked() else ""),
                report_figures_dir=self.report_figures_edit.text().strip(),
                report_pdf_path=(self.report_pdf_edit.text().strip() if self.cap_report_cb.isChecked() else ""),
                report_pdf_bindings=self._pdf_bindings_collect(),
                cog_proxy=self.cog_proxy_edit.text().strip(),
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
