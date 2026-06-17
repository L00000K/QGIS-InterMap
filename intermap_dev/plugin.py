"""
InterMap Dev Reloader — companion plugin for InterMap development.

Watches the InterMap source directory and hot-reloads the plugin in QGIS
whenever any Python source file or vendor asset changes.

Setup (one time):
    Web → InterMap Dev → Set Source Path…  → point at <repo>/intermap/
"""

import os
import shutil

from qgis.PyQt.QtCore import QFileSystemWatcher, QSettings, QTimer
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.core import Qgis

_SETTINGS_KEY = "InterMapDev/sourcePath"
_PLUGIN_NAME = "intermap"
_DEBOUNCE_MS = 600  # wait this long after last change before reloading


class DevReloadPlugin:
    def __init__(self, iface):
        self.iface = iface
        self._watcher = QFileSystemWatcher()
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._do_reload)
        self._watcher.fileChanged.connect(self._on_change)
        self._watcher.directoryChanged.connect(self._on_change)
        self._actions = []

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        self._add_action("Set Source Path…", self._pick_source)
        self._add_action("Reload Now", self._do_reload)

        src = QSettings().value(_SETTINGS_KEY, "")
        if src and os.path.isdir(src):
            self._watch(src)
        else:
            self.iface.messageBar().pushMessage(
                "InterMap Dev",
                "Source path not set. Use Web → InterMap Dev → Set Source Path…",
                level=Qgis.Warning,
                duration=8,
            )

    def unload(self):
        for action in self._actions:
            self.iface.removePluginWebMenu("InterMap Dev", action)
        self._watcher.removePaths(self._watcher.files() + self._watcher.directories())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_action(self, label, slot):
        action = QAction(label)
        action.triggered.connect(slot)
        self.iface.addPluginToWebMenu("InterMap Dev", action)
        self._actions.append(action)

    def _pick_source(self):
        current = QSettings().value(_SETTINGS_KEY, "")
        path = QFileDialog.getExistingDirectory(
            None,
            "Select intermap/ source directory",
            current or os.path.expanduser("~"),
        )
        if not path:
            return
        if not os.path.isfile(os.path.join(path, "metadata.txt")):
            QMessageBox.warning(
                None,
                "InterMap Dev",
                f"No metadata.txt found in:\n{path}\n\nPlease select the intermap/ folder.",
            )
            return
        QSettings().setValue(_SETTINGS_KEY, path)
        self._watch(path)
        self.iface.messageBar().pushMessage(
            "InterMap Dev", f"Watching: {path}", level=Qgis.Success, duration=4
        )

    # ------------------------------------------------------------------
    # File watching
    # ------------------------------------------------------------------

    def _watch(self, src_dir):
        # Clear existing watches
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())

        # Watch the top-level directory (catches new files / deletions)
        self._watcher.addPath(src_dir)

        # Watch every individual file so content changes are detected
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            self._watcher.addPath(root)
            for fname in files:
                if not fname.endswith((".pyc", ".pyo")):
                    self._watcher.addPath(os.path.join(root, fname))

    def _on_change(self, path):
        # Re-add the path if it was re-created (editors often write new inode)
        if os.path.exists(path) and path not in self._watcher.files() + self._watcher.directories():
            self._watcher.addPath(path)
        self._debounce.start(_DEBOUNCE_MS)

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def _do_reload(self):
        src = QSettings().value(_SETTINGS_KEY, "")
        if not src or not os.path.isdir(src):
            self.iface.messageBar().pushMessage(
                "InterMap Dev", "Source path not set.", level=Qgis.Warning, duration=4
            )
            return

        dst = self._plugin_install_dir()
        if not dst:
            return

        try:
            self._install(src, dst)
            self._reload_plugin()
            self.iface.messageBar().pushMessage(
                "InterMap Dev", "InterMap reloaded.", level=Qgis.Success, duration=3
            )
        except Exception as exc:
            self.iface.messageBar().pushMessage(
                "InterMap Dev", f"Reload failed: {exc}", level=Qgis.Critical, duration=8
            )

    def _install(self, src, dst):
        plugin_dst = os.path.join(dst, _PLUGIN_NAME)
        if os.path.exists(plugin_dst):
            shutil.rmtree(plugin_dst)
        shutil.copytree(
            src,
            plugin_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

    def _reload_plugin(self):
        import importlib
        import qgis.utils as qu

        # Unload
        if _PLUGIN_NAME in qu.plugins:
            qu.plugins[_PLUGIN_NAME].unload()
            del qu.plugins[_PLUGIN_NAME]

        # Evict all cached modules for this plugin so re-import picks up changes
        to_remove = [k for k in __import__("sys").modules if k == _PLUGIN_NAME or k.startswith(_PLUGIN_NAME + ".")]
        for mod in to_remove:
            del __import__("sys").modules[mod]

        # Reload
        qu.loadPlugin(_PLUGIN_NAME)
        qu.startPlugin(_PLUGIN_NAME)

    def _plugin_install_dir(self):
        import qgis.utils as qu
        # The plugins folder is one level above any loaded plugin's __file__
        for name, plugin in qu.plugins.items():
            plugin_file = getattr(plugin, "__module__", None)
            if plugin_file:
                mod = __import__("sys").modules.get(plugin_file)
                if mod and hasattr(mod, "__file__") and mod.__file__:
                    return os.path.dirname(os.path.dirname(mod.__file__))

        # Fallback: derive from this plugin's own location
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
