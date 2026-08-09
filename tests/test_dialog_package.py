"""
Structural tests for the intermap.dialog package (imported via the qgis mock).

The dialog is Qt UI and can't be driven headlessly, but these tests lock in
the package contract: it imports cleanly, the public class exists with its
mixin composition, and no mixin accidentally shadows another's methods.
"""
import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "qgis_mock"))
sys.path.insert(0, os.path.dirname(_HERE))


class DialogPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import intermap.dialog
        cls.mod = intermap.dialog
        cls.dlg = intermap.dialog.WebMapExportDialog

    def test_public_api(self):
        self.assertTrue(hasattr(self.mod, "WebMapExportDialog"))
        self.assertEqual(self.mod.__all__, ["WebMapExportDialog"])

    def test_mixin_composition(self):
        names = [c.__name__ for c in self.dlg.__mro__]
        for mixin in ("RichTextMixin", "ConfigsMixin", "MapInfoTabMixin",
                      "MapViewsTabMixin", "LayersTabMixin",
                      "ExportTabMixin"):
            self.assertIn(mixin, names)

    def test_scrollable_wraps_tab_pages(self):
        # Every tab page must be made scrollable so a tall page can never hide
        # the export/close bar (the "can't reach the Export button" bug).
        from qgis.PyQt.QtWidgets import QScrollArea, QWidget
        wrapped = self.dlg._scrollable(QWidget())
        self.assertIsInstance(wrapped, QScrollArea)

    def test_scrollable_passes_through_existing_scrollarea(self):
        # Pages that already provide their own scroll area (Map Info, Map
        # Views) are returned unchanged — no double scrollbars.
        from qgis.PyQt.QtWidgets import QScrollArea
        sa = QScrollArea()
        self.assertIs(self.dlg._scrollable(sa), sa)

    def test_no_method_shadowing_between_mixins(self):
        seen = {}
        for klass in self.dlg.__mro__:
            if not klass.__name__.endswith("Mixin"):
                continue
            for name in vars(klass):
                if name.startswith("__"):
                    continue
                self.assertNotIn(
                    name, seen,
                    "%s defined in both %s and %s" % (name, seen.get(name), klass.__name__))
                seen[name] = klass.__name__

    def test_core_entry_points_present(self):
        for name in ("_export", "_build_ui", "_load_settings",
                     "_save_settings", "_collect_state", "_apply_state",
                     "_capture_canvas_extent", "_switch_tab",
                     "_build_project_tab", "_build_export_settings_tab",
                     "_build_3d_tab", "_build_report_tab",
                     "_update_capability_tabs", "_update_config_caps_label",
                     "_mv_show_layers_in_canvas", "_mv_copy_extent_from_view",
                     "_mv_copy_layers_from_view", "_mv_pick_other_view",
                     "_connect_project_layer_signals",
                     "_refresh_layers_preserving_selection",
                     "_checked_layer_ids", "_set_checked_layer_ids"):
            self.assertTrue(callable(getattr(self.dlg, name, None)), name)

    def test_tab_constants(self):
        self.assertEqual(self.dlg._MAP_VIEWS_TAB, 3)

    def test_plugin_entry_module_imports(self):
        import intermap.plugin
        self.assertTrue(hasattr(intermap.plugin, "WebMapExporterPlugin"))

    def test_dialog_builds_headless_with_capability_tabs(self):
        # Build the whole dock against the mock to prove the capability-builder
        # restructure constructs: 7 tabs (Project, Layers, 4 capability tabs,
        # Export settings), capability→tab map wired, no Lite/Pro machinery.
        class _Canvas:
            def __getattr__(self, n): return lambda *a, **k: _Canvas()

        class _Iface:
            def mainWindow(self): return None
            def mapCanvas(self): return _Canvas()
            def __getattr__(self, n): return lambda *a, **k: None

        dlg = self.dlg(_Iface())
        self.assertEqual(len(dlg._nav_btns), 7)
        # Export settings is last so the capability indices stay stable.
        self.assertEqual([idx for _cb, idx in dlg._cap_tab_map], [2, 3, 4, 5])
        # Lite/Pro mode machinery is gone — check the real classes' own dicts
        # (hasattr is unreliable through the permissive placeholder base).
        own = set()
        for klass in type(dlg).__mro__:
            if klass.__module__.startswith("intermap."):
                own |= set(vars(klass))
        self.assertNotIn("_set_mode", own)
        self.assertNotIn("_build_lite_layers_tab", own)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class Qt6ReadinessTests(unittest.TestCase):
    """Guard the QGIS 4 / Qt6 port against regressions.

    PyQt6 removed the unscoped enum aliases and exec_(), and moved QAction, so
    any of these creeping back in breaks the plugin on QGIS 4 while still
    working perfectly on QGIS 3.
    """

    _SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "intermap")

    def _sources(self):
        for root, dirs, files in os.walk(self._SRC):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(root, name)
                    with open(path, encoding="utf-8") as fh:
                        yield path, fh.read()

    def test_no_exec_underscore(self):
        bad = [p for p, src in self._sources() if ".exec_(" in src]
        self.assertEqual(bad, [], "exec_() was removed in PyQt6; use exec()")

    def test_no_unscoped_qt_enums(self):
        # Every Qt.<Name> must be an enum class (Qt.CheckState.Checked), not a
        # bare member. Enum classes are the only CamelCase names allowed here.
        allowed = {
            "CheckState", "ItemDataRole", "BrushStyle", "PenStyle", "TextFormat",
            "AlignmentFlag", "ItemFlag", "ScrollBarPolicy", "CursorShape",
            "DockWidgetArea", "MouseButton", "DropAction", "TransformationMode",
            "AspectRatioMode", "GlobalColor", "WindowType", "Orientation",
            "KeyboardModifier", "Key", "WidgetAttribute", "ConnectionType",
            "FocusPolicy", "ContextMenuPolicy", "TextInteractionFlag",
        }
        bad = []
        for path, src in self._sources():
            for member in re.findall(r"\bQt\.([A-Za-z_]+)", src):
                if member not in allowed:
                    bad.append("%s: Qt.%s" % (os.path.basename(path), member))
        self.assertEqual(bad, [], "unscoped Qt enum members break on PyQt6")

    def test_qaction_comes_from_the_compat_module(self):
        # QAction moved from QtWidgets to QtGui in Qt6.
        bad = [p for p, src in self._sources()
               if os.path.basename(p) != "compat.py"
               and re.search(r"from qgis\.PyQt\.QtWidgets import[^\n]*\bQAction\b", src)]
        self.assertEqual(bad, [], "import QAction from intermap.compat instead")

    def test_no_removed_qgis_enum_aliases(self):
        # Resolved through intermap/compat.py so QGIS 4 can drop the aliases.
        bad = []
        for path, src in self._sources():
            if os.path.basename(path) == "compat.py":
                continue
            for alias in ("QgsMapLayer.VectorLayer", "QgsMapLayer.RasterLayer",
                          "QgsWkbTypes.PolygonGeometry", "Qgis.Warning"):
                if alias in src:
                    bad.append("%s: %s" % (os.path.basename(path), alias))
        self.assertEqual(bad, [], "use the constants in intermap.compat")
