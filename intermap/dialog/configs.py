"""Named export configurations: config bar, per-project persistence, import/export."""
import os
import json
import datetime
from qgis.PyQt.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QLineEdit,
    QMessageBox, QWidget, QInputDialog, QMenu,
)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.core import QgsProject
from .constants import _SETTINGS_KEY, _INSTANCES_KEY


class ConfigsMixin:
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

        # Live summary of the ticked map-profile capabilities, as "name - number"
        # where the number is the capability's tab position in the nav bar.
        self.config_caps_label = QLabel("")
        self.config_caps_label.setObjectName("icConfigCaps")
        self.config_caps_label.setTextFormat(Qt.RichText)
        self.config_caps_label.setToolTip("Map profile features switched on for this map")
        bar_hl.addWidget(self.config_caps_label)

        self._update_config_bar()
        self._update_config_caps_label()
        return bar

    # Capability label text -> the checkbox attribute that switches it on.
    _CAP_RIBBON = (
        ("Title block", "cap_title_cb"),
        ("Map views",   "cap_views_cb"),
        ("Report",      "cap_report_cb"),
        ("3D",          "feat_3d_cb"),
    )

    def _update_config_caps_label(self):
        """Refresh the ribbon's 'Title block - 3 · Report - 5' capability summary."""
        # Look widgets up in __dict__: they are always set as instance attributes,
        # and this stays correct under the permissive test double used by the
        # headless dialog tests, where getattr() never raises.
        label = self.__dict__.get("config_caps_label")
        if label is None:
            return
        import html as _h
        parts = []
        cap_tabs = {}
        for cb, idx in (self.__dict__.get("_cap_tab_map") or []):
            cap_tabs[id(cb)] = idx
        for name, attr in self._CAP_RIBBON:
            cb = self.__dict__.get(attr)
            if cb is None or not cb.isChecked():
                continue
            num = cap_tabs.get(id(cb))
            parts.append(f"{_h.escape(name)} - {num}" if num is not None else _h.escape(name))
        if parts:
            label.setText("<span style='color:#6B7280;'>" + "  ·  ".join(parts) + "</span>")
        else:
            label.setText("<span style='color:#9CA3AF;'>Simple map</span>")

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
        new_act      = menu.addAction("New blank config…")
        switch_act   = menu.addAction("Switch / Load…")
        save_as_act  = menu.addAction("Save As…")
        menu.addSeparator()
        export_act   = menu.addAction("Export config to file…")
        import_act   = menu.addAction("Import config from file…")
        menu.addSeparator()
        del_act      = menu.addAction("Delete")
        btn = self.sender()
        action = menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action == new_act:
            self._new_blank_config()
        elif action == switch_act:
            self._config_bar_load()
        elif action == save_as_act:
            self._instance_save_as()
        elif action == export_act:
            self._config_export()
        elif action == import_act:
            self._config_import()
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
            "capabilities": {
                "title":  self.cap_title_cb.isChecked(),
                "views":  self.cap_views_cb.isChecked(),
                "report": self.cap_report_cb.isChecked(),
                "3d":     self.feat_3d_cb.isChecked(),
            },
            "theme":                 self.export_theme_combo.currentData(),
            "features": {
                "identify":     self.feat_identify_cb.isChecked(),
                "attr_table":   self.feat_attr_table_cb.isChecked(),
                "attr_csv":     self.feat_attr_csv_cb.isChecked(),
                "attr_geojson": self.feat_attr_geojson_cb.isChecked(),
                "data_export":  self.feat_data_export_cb.isChecked(),
                "measure":      self.feat_measure_cb.isChecked(),
                "filter":       self.feat_filter_cb.isChecked(),
                "search":       self.feat_search_cb.isChecked(),
                "minimap":      self.feat_minimap_cb.isChecked(),
                "fancy_labels": self.feat_fancy_labels_cb.isChecked(),
                "changelog":    self.feat_changelog_cb.isChecked(),
                "sketch":       self.feat_sketch_cb.isChecked(),
                "feat_3d":      self.feat_3d_cb.isChecked(),
                "cesium_ion_token": self.cesium_ion_token_edit.text().strip(),
                "google_maps_key":  self.google_maps_key_edit.text().strip(),
                "cog_proxy":        self.cog_proxy_edit.text().strip(),
                "extrude_field":       self.extrude_field_edit.text().strip(),
                "extrude_scale":       self.extrude_scale_spin.value(),
                "elevation_raster_id": self.elevation_raster_combo.currentData() or "",
                "report_md_path":      self.report_md_edit.text().strip(),
                "report_figures_dir":  self.report_figures_edit.text().strip(),
                "report_pdf_path":     self.report_pdf_edit.text().strip(),
                "report_pdf_bindings": self._pdf_bindings_collect(),
            },
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

        feats = state.get("features", {})
        _feat_map = [
            ("identify",     "feat_identify_cb"),
            ("attr_table",   "feat_attr_table_cb"),
            ("attr_csv",     "feat_attr_csv_cb"),
            ("attr_geojson", "feat_attr_geojson_cb"),
            ("data_export",  "feat_data_export_cb"),
            ("measure",      "feat_measure_cb"),
            ("filter",       "feat_filter_cb"),
            ("search",       "feat_search_cb"),
            ("minimap",      "feat_minimap_cb"),
            ("fancy_labels", "feat_fancy_labels_cb"),
            ("changelog",    "feat_changelog_cb"),
            ("sketch",       "feat_sketch_cb"),
            ("feat_3d",      "feat_3d_cb"),
        ]
        for key, attr in _feat_map:
            if key in feats:
                getattr(self, attr).setChecked(bool(feats[key]))
        if "cesium_ion_token" in feats:
            self.cesium_ion_token_edit.setText(feats["cesium_ion_token"])
        if "google_maps_key" in feats:
            self.google_maps_key_edit.setText(feats["google_maps_key"])
        if "cog_proxy" in feats:
            self.cog_proxy_edit.setText(feats["cog_proxy"])
        if "extrude_field" in feats:
            self.extrude_field_edit.setText(feats["extrude_field"])
        if "extrude_scale" in feats:
            try:
                self.extrude_scale_spin.setValue(float(feats["extrude_scale"]))
            except Exception:
                pass
        if "elevation_raster_id" in feats:
            er_id = feats["elevation_raster_id"]
            if er_id:
                idx = self.elevation_raster_combo.findData(er_id)
                if idx >= 0:
                    self.elevation_raster_combo.setCurrentIndex(idx)
        if "report_md_path" in feats:
            self.report_md_edit.setText(feats["report_md_path"])
        if "report_figures_dir" in feats:
            self.report_figures_edit.setText(feats["report_figures_dir"])
        if "report_pdf_path" in feats:
            self.report_pdf_edit.setText(feats["report_pdf_path"])
        if "report_pdf_bindings" in feats:
            self._pdf_bindings_apply(feats["report_pdf_bindings"])

        # Capability switches (which map profile / tabs are active). Falls back
        # to inferring from content for configs saved before capabilities.
        caps = state.get("capabilities")
        if caps is None:
            caps = {
                "title":  bool(info.get("enabled", True)),
                "views":  bool(state.get("map_views")),
                "report": bool(feats.get("report_md_path") or feats.get("report_pdf_path")),
                "3d":     bool(feats.get("feat_3d")),
            }
        self.cap_title_cb.setChecked(bool(caps.get("title", True)))
        self.cap_views_cb.setChecked(bool(caps.get("views", False)))
        self.cap_report_cb.setChecked(bool(caps.get("report", False)))
        self.feat_3d_cb.setChecked(bool(caps.get("3d", False)))
        self._update_capability_tabs()

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

    def _config_export(self):
        name = self._loaded_instance_name
        state = self._collect_state()
        default_name = f"{name}.intermap.json" if name else "intermap_config.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export config", default_name, "InterMap config (*.intermap.json);;JSON (*.json)"
        )
        if not path:
            return
        payload = {
            "_intermap_config_version": 1,
            "name": name or "",
            "exported": datetime.datetime.now().isoformat(timespec="seconds"),
            "state": state,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            self.iface.messageBar().pushInfo("InterMap", f"Config exported to {os.path.basename(path)}")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _config_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import config", "", "InterMap config (*.intermap.json *.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import failed", f"Could not read file:\n{exc}")
            return
        if not isinstance(payload, dict):
            QMessageBox.critical(self, "Import failed", "File does not contain a valid InterMap config.")
            return

        # Support both wrapped format (with _intermap_config_version) and bare state dicts
        if "_intermap_config_version" in payload:
            state = payload.get("state", {})
            suggested_name = payload.get("name") or os.path.splitext(os.path.basename(path))[0]
        elif "layer_names" in payload or "map_views" in payload:
            state = payload
            suggested_name = os.path.splitext(os.path.basename(path))[0]
        else:
            QMessageBox.critical(self, "Import failed", "File does not contain a valid InterMap config.")
            return

        name, ok = QInputDialog.getText(
            self, "Import config", "Save imported config as:", QLineEdit.Normal, suggested_name
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Please enter a name.")
            return

        existing = self._instances_load_all()
        if name in existing:
            resp = QMessageBox.question(
                self, "Overwrite?", f"A config named '{name}' already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return

        self._apply_state(state)
        existing[name] = self._collect_state()
        self._instances_save_all(existing)
        self._loaded_instance_name = name
        self._has_unsaved_changes = False
        self._update_config_bar()

        missing = self._missing_layer_names(state.get("layer_names", []))
        if missing:
            QMessageBox.information(
                self, "Imported with missing layers",
                "Config '{}' imported.\n\nLayers not in current project (skipped):\n  • {}".format(
                    name, "\n  • ".join(missing))
            )
        else:
            self.iface.messageBar().pushInfo("InterMap", f"Config '{name}' imported.")
