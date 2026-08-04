"""Measure dialog layout geometry against real Qt, and print JSON.

Run as a subprocess by test_dialog_layout.py: it wires qgis.PyQt to the real
PyQt5 so Qt performs genuine layout, while qgis.core stays on the mock. That
replacement is process-wide, hence the isolation.

Usage:  QT_QPA_PLATFORM=offscreen python3 tests/qt_layout_probe.py
"""
import importlib
import importlib.util
import json
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_MOCK = os.path.join(_HERE, "qgis_mock", "qgis")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _install_qgis_shim():
    qgis_pkg = types.ModuleType("qgis")
    qgis_pkg.__path__ = []
    sys.modules["qgis"] = qgis_pkg

    pyqt = types.ModuleType("qgis.PyQt")
    pyqt.__path__ = []
    sys.modules["qgis.PyQt"] = pyqt
    qgis_pkg.PyQt = pyqt

    for name in ("QtWidgets", "QtCore", "QtGui", "QtSvg", "QtNetwork"):
        try:
            mod = importlib.import_module("PyQt5." + name)
        except Exception:
            continue
        sys.modules["qgis.PyQt." + name] = mod
        setattr(pyqt, name, mod)

    spec = importlib.util.spec_from_file_location(
        "qgis.core", os.path.join(_MOCK, "core.py"))
    core = importlib.util.module_from_spec(spec)
    sys.modules["qgis.core"] = core
    spec.loader.exec_module(core)
    qgis_pkg.core = core

    gui = types.ModuleType("qgis.gui")

    class _Any:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, n):
            return lambda *a, **k: None

    gui.__getattr__ = lambda n: _Any
    sys.modules["qgis.gui"] = gui
    qgis_pkg.gui = gui


class _Canvas:
    def __getattr__(self, n):
        return lambda *a, **k: _Canvas()


class _Iface:
    def mainWindow(self):
        return None

    def mapCanvas(self):
        return _Canvas()

    def __getattr__(self, n):
        return lambda *a, **k: None


def _scan_layouts(root, tag, findings):
    """Flag two things across every vertical layout under `root`:

    gaps  — spare height landing *between* items instead of at the bottom
    (items should stack tight), measured on layout items so a nested
    horizontal row is not mistaken for a gap.

    top   — the first item sitting well below the top of its container.
    """
    from PyQt5.QtWidgets import QVBoxLayout, QGroupBox

    def name(w):
        if w is None:
            return "<layout>"
        if isinstance(w, QGroupBox) and w.title():
            return "box:" + w.title()
        return w.objectName() or type(w).__name__

    for lay in root.findChildren(QVBoxLayout):
        items = []
        for i in range(lay.count()):
            item = lay.itemAt(i)
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            if item.spacerItem() is not None:
                continue                      # spacers are what we want to see
            geom = item.geometry()
            if geom.height() <= 0:
                continue
            items.append((geom, widget))
        if len(items) < 2:
            continue
        spacing = max(lay.spacing(), 0)
        for (ga, wa), (gb, wb) in zip(items, items[1:]):
            gap = gb.y() - (ga.y() + ga.height()) - spacing
            if gap > 3:
                findings.append({"where": tag, "after": name(wa),
                                 "before": name(wb), "gap": gap})


def scan_all_tabs():
    """Walk every tab in several states and report layout gaps."""
    from PyQt5.QtWidgets import QApplication, QScrollArea
    app = QApplication.instance() or QApplication(sys.argv)
    sys.path.insert(0, _REPO)
    from intermap.dialog import WebMapExportDialog

    dlg = WebMapExportDialog(_Iface())
    dlg.show()
    for cb in (dlg.cap_title_cb, dlg.cap_views_cb, dlg.cap_report_cb, dlg.feat_3d_cb):
        cb.setChecked(True)
    app.processEvents()

    tabs = ["Project", "Layers", "Title block", "Map Views",
            "Report", "3D", "Export settings"]
    findings = []
    for height in (700, 1100, 1600):
        for collapsed in (False, True):
            dlg.resize(460, height)
            app.processEvents()
            for btn in ("_dm_toggle_btn", "_pi_toggle_btn",
                        "_dc_toggle_btn", "_cl_toggle_btn"):
                w = getattr(dlg, btn, None)
                if w is not None:
                    w.setChecked(not collapsed)
            # (the map-view sub-panels were replaced by Set menus)
            app.processEvents()
            for selected in (False, True):
                if selected and dlg.map_views_list_widget.count() == 0:
                    dlg._map_view_add()
                app.processEvents()
                for idx, name in enumerate(tabs):
                    dlg._switch_tab(idx)
                    app.processEvents()
                    page = dlg._tab_stack.widget(idx)
                    inner = (page.widget()
                             if isinstance(page, QScrollArea) and page.widget()
                             else page)
                    tag = "%s h=%d %s" % (
                        name, height, "collapsed" if collapsed else "open")
                    _scan_layouts(inner, tag, findings)
    app.quit()
    return findings


def measure():
    from PyQt5.QtWidgets import QApplication, QGroupBox
    app = QApplication(sys.argv)
    sys.path.insert(0, _REPO)
    from intermap.dialog import WebMapExportDialog

    out = {}
    dlg = WebMapExportDialog(_Iface())
    dlg.resize(460, 1400)
    dlg.show()
    app.processEvents()

    # Map Views: the list must sit at the top whether or not a view is selected.
    dlg._switch_tab(dlg._MAP_VIEWS_TAB)
    app.processEvents()
    out["mv_list_y_no_selection"] = dlg.map_views_list_widget.y()
    dlg._map_view_add()
    app.processEvents()
    out["mv_list_y_with_selection"] = dlg.map_views_list_widget.y()

    # Title block: sections must not absorb spare height, or their form rows
    # spread and the text boxes drift to the bottom.
    dlg._switch_tab(2)
    for btn in ("_dm_toggle_btn", "_pi_toggle_btn", "_dc_toggle_btn", "_cl_toggle_btn"):
        w = getattr(dlg, btn, None)
        if w is not None:
            w.setChecked(False)
    app.processEvents()
    page = dlg._tab_stack.widget(2)
    inner = page.widget() if hasattr(page, "widget") and page.widget() else page
    slack = {}
    for box in inner.findChildren(QGroupBox):
        if box.isVisible():
            slack[box.title()] = box.height() - box.sizeHint().height()
    out["title_block_group_slack"] = slack
    out["description_y_in_box"] = dlg.info_text_edit.mapTo(
        dlg.info_text_edit.parent(), dlg.info_text_edit.rect().topLeft()).y()

    app.quit()
    return out


if __name__ == "__main__":
    _install_qgis_shim()
    if "--gaps" in sys.argv:
        print(json.dumps(scan_all_tabs()))
    else:
        print(json.dumps(measure()))
