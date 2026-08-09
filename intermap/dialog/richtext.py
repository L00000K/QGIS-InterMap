"""Rich-text editor toolbars shared by the notes/info fields."""
from qgis.PyQt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QTextEdit, QWidget, QComboBox, QInputDialog,
)
from qgis.PyQt.QtGui import (
    QColor, QFont, QTextCharFormat, QTextListFormat, QTextLength,
    QTextTableFormat,
)
from qgis.PyQt.QtCore import Qt, QBuffer, QByteArray
from .constants import _PURPLE


class RichTextMixin:
    @staticmethod
    def _set_richtext(edit, text):
        if text and ("<html" in text[:80] or "<!DOCTYPE" in text[:80]):
            edit.setHtml(text)
        else:
            edit.setPlainText(text or "")

    def _make_rt_btn(self, label, tip, checkable=False, width=24, label_style=""):
        """Small toolbar button for rich-text toolbars."""
        btn = QPushButton(label)
        btn.setToolTip(tip)
        btn.setFixedSize(width, 22)
        btn.setCheckable(checkable)
        css = (
            f"QPushButton {{ font-size:10px; padding:0; border:1px solid #D1D5DB; border-radius:2px; {label_style} }}"
            f"QPushButton:checked {{ background:#ede9ff; border-color:{_PURPLE}; }}"
            f"QPushButton:hover {{ border-color:#9CA3AF; }}"
        )
        btn.setStyleSheet(css)
        return btn

    def _wire_fmt_sync(self, edit, b_btn, i_btn, u_btn, s_btn=None):
        """Sync B/I/U/S button checked state to *edit*'s current cursor format."""
        def _sync(_=None):
            fmt = edit.currentCharFormat()
            for btn in [b_btn, i_btn, u_btn, s_btn]:
                if btn:
                    btn.blockSignals(True)
            b_btn.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
            i_btn.setChecked(fmt.fontItalic())
            u_btn.setChecked(fmt.fontUnderline())
            if s_btn:
                s_btn.setChecked(fmt.fontStrikeOut())
            for btn in [b_btn, i_btn, u_btn, s_btn]:
                if btn:
                    btn.blockSignals(False)
        edit.currentCharFormatChanged.connect(_sync)

    def _build_richtext_toolbar(self, edit):
        """Compact B / I / U + ⤢ expand toolbar for inline text fields."""
        bar = QWidget()
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(0, 0, 0, 2)
        hl.setSpacing(2)

        b = self._make_rt_btn("B", "Bold",      checkable=True, label_style="font-weight:bold")
        i = self._make_rt_btn("I", "Italic",    checkable=True, label_style="font-style:italic")
        u = self._make_rt_btn("U", "Underline", checkable=True, label_style="text-decoration:underline")
        for btn in (b, i, u):
            hl.addWidget(btn)

        hl.addStretch()

        expand_btn = self._make_rt_btn("⤢", "Expand editor", width=22)
        hl.addWidget(expand_btn)

        def _apply(_=None):
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold if b.isChecked() else QFont.Weight.Normal)
            fmt.setFontItalic(i.isChecked())
            fmt.setFontUnderline(u.isChecked())
            edit.textCursor().mergeCharFormat(fmt)
            edit.mergeCurrentCharFormat(fmt)

        b.clicked.connect(_apply)
        i.clicked.connect(_apply)
        u.clicked.connect(_apply)
        self._wire_fmt_sync(edit, b, i, u)
        expand_btn.clicked.connect(lambda: self._rt_expand(edit))
        return bar

    def _build_full_richtext_toolbar(self, edit):
        """Full rich-text toolbar for the expanded editor panel."""
        bar = QWidget()
        bar.setObjectName("greyBox")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(3)

        def sep():
            s = QLabel("|")
            s.setStyleSheet("color:#D1D5DB; padding:0 2px;")
            hl.addWidget(s)

        # ── Character formatting ──────────────────────────────────────────────
        b = self._make_rt_btn("B", "Bold",          checkable=True, label_style="font-weight:bold")
        i = self._make_rt_btn("I", "Italic",        checkable=True, label_style="font-style:italic")
        u = self._make_rt_btn("U", "Underline",     checkable=True, label_style="text-decoration:underline")
        s = self._make_rt_btn("S", "Strikethrough", checkable=True, label_style="text-decoration:line-through")
        for btn in (b, i, u, s):
            hl.addWidget(btn)

        def _apply_char(_=None):
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold if b.isChecked() else QFont.Weight.Normal)
            fmt.setFontItalic(i.isChecked())
            fmt.setFontUnderline(u.isChecked())
            fmt.setFontStrikeOut(s.isChecked())
            edit.textCursor().mergeCharFormat(fmt)
            edit.mergeCurrentCharFormat(fmt)

        for btn in (b, i, u, s):
            btn.clicked.connect(_apply_char)
        self._wire_fmt_sync(edit, b, i, u, s)

        sep()

        # ── Font size ─────────────────────────────────────────────────────────
        size_combo = QComboBox()
        size_combo.setFixedWidth(52)
        size_combo.setEditable(True)
        for sz in ("8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "36", "48"):
            size_combo.addItem(sz)
        size_combo.setCurrentText("10")
        size_combo.setToolTip("Font size")
        hl.addWidget(size_combo)

        def _set_size(txt):
            try:
                pts = float(txt)
                if pts > 0:
                    fmt = QTextCharFormat()
                    fmt.setFontPointSize(pts)
                    edit.textCursor().mergeCharFormat(fmt)
            except ValueError:
                pass

        size_combo.currentTextChanged.connect(_set_size)

        def _sync_size(_=None):
            sz = edit.currentCharFormat().fontPointSize()
            if sz > 0:
                size_combo.blockSignals(True)
                size_combo.setCurrentText(str(int(sz)))
                size_combo.blockSignals(False)

        edit.currentCharFormatChanged.connect(_sync_size)

        # ── Font colour ───────────────────────────────────────────────────────
        colour_btn = self._make_rt_btn("A", "Text colour", width=28, label_style="color:#DC2626;font-weight:bold")
        hl.addWidget(colour_btn)

        def _pick_colour():
            from qgis.PyQt.QtWidgets import QColorDialog
            col = QColorDialog.getColor(edit.currentCharFormat().foreground().color(), self, "Text colour")
            if col.isValid():
                fmt = QTextCharFormat()
                fmt.setForeground(col)
                edit.textCursor().mergeCharFormat(fmt)

        colour_btn.clicked.connect(_pick_colour)

        sep()

        # ── Alignment ─────────────────────────────────────────────────────────
        al = self._make_rt_btn("≡L", "Align left",    checkable=True, width=28)
        ac = self._make_rt_btn("≡C", "Align centre",  checkable=True, width=28)
        ar = self._make_rt_btn("≡R", "Align right",   checkable=True, width=28)
        for btn in (al, ac, ar):
            hl.addWidget(btn)

        def _align(alignment, btn):
            for other in (al, ac, ar):
                other.blockSignals(True)
                other.setChecked(other is btn)
                other.blockSignals(False)
            edit.setAlignment(alignment)

        al.clicked.connect(lambda: _align(Qt.AlignmentFlag.AlignLeft,    al))
        ac.clicked.connect(lambda: _align(Qt.AlignmentFlag.AlignHCenter, ac))
        ar.clicked.connect(lambda: _align(Qt.AlignmentFlag.AlignRight,   ar))
        al.setChecked(True)

        sep()

        # ── Lists ─────────────────────────────────────────────────────────────
        bl = self._make_rt_btn("•≡", "Bullet list",   width=28)
        nl = self._make_rt_btn("1.≡", "Numbered list", width=30)
        hl.addWidget(bl)
        hl.addWidget(nl)

        def _insert_list(style):
            cursor = edit.textCursor()
            fmt = QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(1)
            cursor.createList(fmt)

        bl.clicked.connect(lambda: _insert_list(QTextListFormat.ListDisc))
        nl.clicked.connect(lambda: _insert_list(QTextListFormat.ListDecimal))

        sep()

        # ── Link ──────────────────────────────────────────────────────────────
        link_btn = self._make_rt_btn("🔗", "Insert hyperlink", width=28)
        hl.addWidget(link_btn)

        def _insert_link():
            cursor = edit.textCursor()
            sel_text = cursor.selectedText()
            url, ok = QInputDialog.getText(self, "Insert link", "URL:", text="https://")
            if not ok or not url.strip():
                return
            display, ok2 = QInputDialog.getText(self, "Insert link", "Display text:", text=sel_text or url)
            if not ok2:
                return
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(url.strip())
            fmt.setForeground(QColor(_PURPLE))
            fmt.setFontUnderline(True)
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                cursor.insertText(display or url, fmt)

        link_btn.clicked.connect(_insert_link)

        # ── Image ─────────────────────────────────────────────────────────────
        img_btn = self._make_rt_btn("🖼", "Insert image", width=28)
        hl.addWidget(img_btn)

        def _insert_image():
            import base64
            path, _ = QFileDialog.getOpenFileName(
                self, "Insert image", "",
                "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
            )
            if not path:
                return
            from qgis.PyQt.QtGui import QImage
            img = QImage(path)
            if img.isNull():
                return
            if img.width() > 600:
                img = img.scaledToWidth(600, Qt.TransformationMode.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            img.save(buf, "PNG")
            b64 = base64.b64encode(bytes(ba)).decode()
            edit.textCursor().insertHtml(
                f'<img src="data:image/png;base64,{b64}" style="max-width:100%">'
            )

        img_btn.clicked.connect(_insert_image)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_btn = self._make_rt_btn("⊞", "Insert table", width=28)
        hl.addWidget(tbl_btn)

        def _insert_table():
            rows, ok = QInputDialog.getInt(self, "Insert table", "Rows:", 2, 1, 20)
            if not ok:
                return
            cols, ok = QInputDialog.getInt(self, "Insert table", "Columns:", 2, 1, 20)
            if not ok:
                return
            tfmt = QTextTableFormat()
            tfmt.setBorder(1)
            tfmt.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
            tfmt.setCellPadding(4)
            tfmt.setCellSpacing(0)
            tfmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            edit.textCursor().insertTable(rows, cols, tfmt)

        tbl_btn.clicked.connect(_insert_table)

        hl.addStretch()
        return bar

    def _build_rt_expand_widget(self):
        """Full-panel rich-text editor overlay (page 1 of _content_stack)."""
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(4)

        # Header row
        hdr = QWidget()
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(0, 0, 0, 0)
        hdr_l.setSpacing(6)
        back_btn = QPushButton("← Done")
        back_btn.setFixedWidth(72)
        back_btn.clicked.connect(self._rt_collapse)
        hdr_l.addWidget(back_btn)
        self._rt_field_label = QLabel("")
        self._rt_field_label.setStyleSheet("font-weight:600; color:#374151;")
        hdr_l.addWidget(self._rt_field_label, 1)
        vl.addWidget(hdr)

        # The shared editor (document is swapped in _rt_expand)
        self._rt_big_edit = QTextEdit()
        self._rt_big_edit.setAcceptRichText(True)

        vl.addWidget(self._build_full_richtext_toolbar(self._rt_big_edit))
        vl.addWidget(self._rt_big_edit, 1)

        self._rt_source_edit = None  # the compact edit currently expanded
        return widget

    def _rt_expand(self, edit):
        """Swap *edit*'s document into the full-panel editor and show it."""
        self._rt_source_edit = edit
        self._rt_big_edit.setDocument(edit.document())
        # Label: try to find a friendly name from the placeholder text
        label = edit.placeholderText() or "Description"
        self._rt_field_label.setText(f"Editing: {label}")
        self._content_stack.setCurrentIndex(1)
        self._rt_big_edit.setFocus()

    def _rt_collapse(self):
        self._rt_source_edit = None
        self._content_stack.setCurrentIndex(0)
