"""Layout regressions, measured against real Qt.

The rest of the suite runs on a permissive mock, which cannot answer geometry
questions — it reports no sizes at all. These checks therefore need real
PyQt5 and are skipped when it is unavailable, so the mock-based suite keeps
working unchanged.

The probe runs in a subprocess because it rebinds qgis.PyQt to real PyQt5
process-wide, which would break every other test in this run.
"""
import json
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROBE = os.path.join(_HERE, "qt_layout_probe.py")


def _pyqt5_available():
    try:
        import importlib
        importlib.import_module("PyQt5.QtWidgets")
        return True
    except Exception:
        return False


@unittest.skipUnless(_pyqt5_available(), "real PyQt5 not installed")
class DialogLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        res = subprocess.run([sys.executable, _PROBE], capture_output=True,
                             text=True, env=env, timeout=180)
        if res.returncode != 0:
            raise unittest.SkipTest("layout probe failed: %s" % res.stderr[-400:])
        cls.geom = json.loads(res.stdout.strip().splitlines()[-1])

    def test_map_views_list_stays_at_top_without_selection(self):
        # The detail pane is hidden until a view is selected. Without a spacer
        # to take the slack the list floated to the middle of the tab and then
        # jumped upward on selection.
        self.assertLessEqual(
            self.geom["mv_list_y_no_selection"], 12,
            "map views list is not top-aligned before a view is selected")

    def test_map_views_list_does_not_move_on_selection(self):
        self.assertEqual(self.geom["mv_list_y_no_selection"],
                         self.geom["mv_list_y_with_selection"],
                         "map views list shifts when a view is selected")

    def test_title_block_sections_do_not_absorb_spare_height(self):
        # A group box left on Qt's default Preferred policy grows to fill the
        # tab, and its form rows spread apart with it — which is what made the
        # text boxes bottom-align once the sections below were collapsed.
        for title, slack in self.geom["title_block_group_slack"].items():
            self.assertLessEqual(
                slack, 8,
                "'%s' grows %dpx beyond its natural height" % (title, slack))


if __name__ == "__main__":
    unittest.main(verbosity=2)
