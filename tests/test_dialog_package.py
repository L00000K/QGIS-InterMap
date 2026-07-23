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
                      "MapViewsTabMixin", "LayersTabMixin", "LiteModeMixin",
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
        for name in ("_export", "_export_lite", "_build_ui", "_load_settings",
                     "_save_settings", "_collect_state", "_apply_state",
                     "_capture_canvas_extent", "_switch_tab", "_set_mode"):
            self.assertTrue(callable(getattr(self.dlg, name, None)), name)

    def test_tab_constants(self):
        self.assertEqual(self.dlg._MAP_VIEWS_TAB, 1)
        self.assertEqual(self.dlg._LITE_TAB, 4)

    def test_plugin_entry_module_imports(self):
        import intermap.plugin
        self.assertTrue(hasattr(intermap.plugin, "WebMapExporterPlugin"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
