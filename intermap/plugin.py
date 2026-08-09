import os
from .compat import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication, Qt


class WebMapExporterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self._dlg = None

    def tr(self, message):
        return QCoreApplication.translate("InterMap", message)

    def initGui(self):
        svg_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        icon = QIcon(svg_path) if os.path.exists(svg_path) else QIcon()
        self.action = QAction(icon, self.tr("InterMap — Interactive Map Package…"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu(self.tr("InterMap"), self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginWebMenu(self.tr("InterMap"), self.action)
        self.iface.removeToolBarIcon(self.action)
        if self._dlg:
            self.iface.removeDockWidget(self._dlg)
            self._dlg.deleteLater()
            self._dlg = None

    def run(self):
        from .version_check import warn_if_unsupported
        warn_if_unsupported(self.iface)
        from .whats_new import check_for_update
        check_for_update(self.iface.mainWindow())
        from .dialog import WebMapExportDialog
        if self._dlg is None:
            self._dlg = WebMapExportDialog(self.iface)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dlg)
        self._dlg.show()
        self._dlg.raise_()
