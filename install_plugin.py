#!/usr/bin/env python3
"""
Install the InterMap plugin (and optional dev reloader) into the active QGIS profile.

Usage:
    python3 install_plugin.py           # installs intermap + intermap_dev
    python3 install_plugin.py --no-dev  # installs intermap only

Or run from within QGIS Python console:
    exec(open('/path/to/install_plugin.py').read())
"""
import os
import shutil
import sys


def get_qgis_plugin_dir():
    candidates = []

    # Linux
    xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    candidates.append(os.path.join(xdg, "QGIS", "QGIS3", "profiles", "default", "python", "plugins"))
    candidates.append(os.path.expanduser("~/.local/share/QGIS/QGIS3/profiles/default/python/plugins"))

    # macOS
    candidates.append(os.path.expanduser(
        "~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
    ))

    # Windows
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(os.path.join(appdata, "QGIS", "QGIS3", "profiles", "default", "python", "plugins"))

    for c in candidates:
        if os.path.isdir(os.path.dirname(c)):
            return c
    return candidates[0]


def install_plugin(src, plugin_dir, name):
    dst = os.path.join(plugin_dir, name)
    os.makedirs(plugin_dir, exist_ok=True)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    print(f"  Installed {name} → {dst}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    no_dev = "--no-dev" in sys.argv

    plugins = [("intermap", "InterMap")]
    if not no_dev and os.path.isdir(os.path.join(script_dir, "intermap_dev")):
        plugins.append(("intermap_dev", "InterMap Dev Reloader"))

    plugin_dir = get_qgis_plugin_dir()
    print(f"Installing to: {plugin_dir}")

    for folder, label in plugins:
        src = os.path.join(script_dir, folder)
        if not os.path.isdir(src):
            print(f"  SKIP {label} — source not found at {src}")
            continue
        install_plugin(src, plugin_dir, folder)

    print()
    print("Done. Restart QGIS and enable the plugin(s) in Plugins → Manage Plugins.")
    if not no_dev:
        print("Then: Web → InterMap Dev → Set Source Path… → point at the intermap/ folder in this repo.")


if __name__ == "__main__":
    main()
