"""Map Info tab: title block, document control, changelog."""
import datetime
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QLineEdit, QCheckBox, QGroupBox, QTextEdit, QFormLayout,
    QWidget, QComboBox, QScrollArea, QGridLayout, QSizePolicy,
)
from qgis.PyQt.QtGui import QFont
from qgis.core import QgsProject
from .constants import _PURPOSE_OPTIONS
from .widgets import _VResizeHandle


class MapInfoTabMixin:
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
        _rev_btn_row = QHBoxLayout()
        _minor_btn = QPushButton("↑ Minor")
        _minor_btn.setToolTip("Increment minor version (e.g. 1.2 → 1.3)")
        _minor_btn.clicked.connect(self._rev_increment_minor)
        _major_btn = QPushButton("↑ Major")
        _major_btn.setToolTip("Increment major version (e.g. 1.2 → 2.0)")
        _major_btn.clicked.connect(self._rev_increment_major)
        _rev_btn_row.addWidget(_minor_btn)
        _rev_btn_row.addWidget(_major_btn)
        _rev_btn_row.addStretch()
        dm_form.addRow("", _rev_btn_row)
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

        # ── Changelog ─────────────────────────────────────────────────────────
        _cl_hdr = QWidget()
        _cl_hdr_l = QHBoxLayout(_cl_hdr)
        _cl_hdr_l.setContentsMargins(0, 4, 0, 0)
        _cl_hdr_l.setSpacing(4)
        self._cl_toggle_btn = QPushButton("▶")
        self._cl_toggle_btn.setFixedSize(18, 18)
        self._cl_toggle_btn.setFlat(True)
        self._cl_toggle_btn.setCheckable(True)
        self._cl_toggle_btn.setChecked(False)
        _cl_hdr_l.addWidget(self._cl_toggle_btn)
        _cl_title_lbl = QLabel("Changelog")
        _cl_title_lbl.setStyleSheet("font-weight: 600;")
        _cl_hdr_l.addWidget(_cl_title_lbl, 1)
        layout.addWidget(_cl_hdr)

        self.cl_widget = QWidget()
        self.cl_widget.setVisible(False)
        cl_vl = QVBoxLayout(self.cl_widget)
        cl_vl.setContentsMargins(6, 4, 6, 4)
        cl_vl.setSpacing(4)

        self.changelog_list = QListWidget()
        self.changelog_list.setMaximumHeight(120)
        self.changelog_list.setFont(QFont("Segoe UI", 8))
        cl_vl.addWidget(self.changelog_list)

        _add_row = QHBoxLayout()
        self.changelog_text_edit = QLineEdit()
        self.changelog_text_edit.setPlaceholderText("Entry description…")
        self.changelog_text_edit.returnPressed.connect(self._changelog_add_entry)
        _add_btn = QPushButton("+ Add")
        _add_btn.setFixedWidth(55)
        _add_btn.clicked.connect(self._changelog_add_entry)
        _add_row.addWidget(self.changelog_text_edit, 1)
        _add_row.addWidget(_add_btn)
        cl_vl.addLayout(_add_row)

        _rm_btn = QPushButton("Remove selected")
        _rm_btn.clicked.connect(self._changelog_remove_entry)
        cl_vl.addWidget(_rm_btn)

        layout.addWidget(self.cl_widget)
        self._cl_toggle_btn.toggled.connect(
            lambda checked: (
                self._cl_toggle_btn.setText("▼" if checked else "▶"),
                self.cl_widget.setVisible(checked),
            )
        )

        # Sections must not absorb spare height. With Qt's default Preferred
        # policy a group box grows to fill the tab and its form rows spread
        # apart, so collapsing the sections below left the title and
        # description boxes drifting toward the bottom of the panel. Pin each
        # section to its natural height and let the stretch below take the
        # slack instead.
        for _i in range(layout.count()):
            _w = layout.itemAt(_i).widget()
            if _w is not None:
                _w.setSizePolicy(_w.sizePolicy().horizontalPolicy(),
                                 QSizePolicy.Maximum)

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

    def _rev_increment_minor(self):
        import re
        txt = self.info_revision_edit.text().strip()
        m = re.search(r'(\d+)\.(\d+)', txt)
        if m:
            new_rev = txt[:m.start()] + f"{m.group(1)}.{int(m.group(2))+1}" + txt[m.end():]
        elif re.search(r'\d+', txt):
            new_rev = txt + ".1"
        else:
            new_rev = "1.1"
        self.info_revision_edit.setText(new_rev)

    def _rev_increment_major(self):
        import re
        txt = self.info_revision_edit.text().strip()
        m = re.search(r'(\d+)\.(\d+)', txt)
        if m:
            new_rev = txt[:m.start()] + f"{int(m.group(1))+1}.0" + txt[m.end():]
        else:
            digits = re.findall(r'\d+', txt)
            new_rev = f"{int(digits[0])+1}.0" if digits else "2.0"
        self.info_revision_edit.setText(new_rev)

    def _changelog_add_entry(self):
        text = self.changelog_text_edit.text().strip()
        if not text:
            return
        rev = self.info_revision_edit.text().strip() or "—"
        date = datetime.datetime.now().strftime("%d/%m/%Y")
        self._changelog.append({"rev": rev, "date": date, "text": text})
        self.changelog_text_edit.clear()
        self._changelog_refresh_list()

    def _changelog_remove_entry(self):
        row = self.changelog_list.currentRow()
        if row < 0:
            return
        # list is shown in reverse order
        real_idx = len(self._changelog) - 1 - row
        if 0 <= real_idx < len(self._changelog):
            self._changelog.pop(real_idx)
        self._changelog_refresh_list()

    def _changelog_refresh_list(self):
        self.changelog_list.clear()
        for e in reversed(self._changelog):
            self.changelog_list.addItem(
                f"[{e.get('rev','—')} – {e.get('date','')}]  {e.get('text','')}"
            )
