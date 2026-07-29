"""
Structural tests for the intermap.dialog package (imported via the qgis mock).

The dialog is Qt UI and can't be driven headlessly, but these tests lock in
the package contract: it imports cleanly, the public class exists with its
mixin composition, and no mixin accidentally shadows another's methods.
"""
import os
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
                     "_update_capability_tabs", "_update_config_caps_label"):
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
