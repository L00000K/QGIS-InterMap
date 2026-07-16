"""
Locating and embedding static assets: Leaflet, Leaflet plugins, vendor files.

All assets are bundled in the plugin's vendor/ directory so exports work
offline; network download is a last-resort fallback for Leaflet itself.
"""
import os
import urllib.request
from typing import Optional

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest


_PLUGIN_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB_DIR         = os.path.join(_PLUGIN_DIR, "lib")
_LEAFLET_VERSION = "1.9.4"
_LEAFLET_URLS = [
    "https://unpkg.com/leaflet@{v}/dist/leaflet.min.{ext}",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/{v}/leaflet.min.{ext}",
]


def _qgis_fetch(url_str: str) -> Optional[str]:
    """
    Download text from url_str using QGIS's network stack (respects proxy /
    auth settings configured in QGIS options) with a fallback to urllib.
    Returns the decoded text or None on failure.
    """
    # QgsBlockingNetworkRequest available since QGIS 3.6
    try:
        from qgis.core import QgsBlockingNetworkRequest
        req = QNetworkRequest(QUrl(url_str))
        blocker = QgsBlockingNetworkRequest()
        err = blocker.get(req)
        if err == QgsBlockingNetworkRequest.NoError:
            return bytes(blocker.reply().content()).decode("utf-8")
    except Exception:
        pass

    # Plain urllib fallback
    try:
        with urllib.request.urlopen(url_str, timeout=20) as r:
            return r.read().decode("utf-8")
    except Exception:
        pass

    return None


_VENDOR_CSS = os.path.join(_PLUGIN_DIR, "vendor", "leaflet.css")
_VENDOR_JS  = os.path.join(_PLUGIN_DIR, "vendor", "leaflet.js")


def _get_leaflet_assets() -> tuple[str, str] | tuple[None, None]:
    """
    Return (css, js) strings for inline embedding.

    Priority:
      1. Bundled vendor/ files shipped with the plugin (always available).
      2. Previously downloaded + cached copy in lib/.
      3. Download from CDN and cache in lib/.
      4. Return (None, None) — caller falls back to CDN <link>/<script> tags.
    """
    # 1. Bundled files — committed to the repo, always present
    if os.path.exists(_VENDOR_CSS) and os.path.exists(_VENDOR_JS):
        with open(_VENDOR_CSS, encoding="utf-8") as f:
            css = f.read()
        with open(_VENDOR_JS, encoding="utf-8") as f:
            js = f.read()
        return css, js

    # 2. Previously cached download
    v        = _LEAFLET_VERSION
    css_path = os.path.join(_LIB_DIR, f"leaflet-{v}.min.css")
    js_path  = os.path.join(_LIB_DIR, f"leaflet-{v}.min.js")
    if os.path.exists(css_path) and os.path.exists(js_path):
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        with open(js_path, encoding="utf-8") as f:
            js = f.read()
        return css, js

    # 3. Download and cache
    os.makedirs(_LIB_DIR, exist_ok=True)
    for tpl in _LEAFLET_URLS:
        css = _qgis_fetch(tpl.format(v=v, ext="css"))
        js  = _qgis_fetch(tpl.format(v=v, ext="js"))
        if css and js:
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(css)
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(js)
            return css, js

    return None, None


# ── Plugin asset specs ────────────────────────────────────────────────────────
_PLUGIN_SPECS = {
    "fullscreen":    ("fullscreen.min.css",  "fullscreen.min.js"),
    "minimap":       ("minimap.min.css",     "minimap.min.js"),
    "search":        ("search.min.css",      "search.min.js"),
    "contextmenu":   ("contextmenu.min.css", "contextmenu.min.js"),
    "geoman":        ("geoman.min.css",      "geoman.min.js"),
    "markercluster": ("markercluster.css",   "markercluster.js"),
}


def _load_plugin_assets() -> dict:
    """
    Return {name: (css_str, js_str)} for each plugin whose vendor files exist.
    Missing plugins degrade silently — JS guards (typeof checks) handle absence.
    """
    vendor = os.path.join(_PLUGIN_DIR, "vendor")
    result = {}
    for name, (css_file, js_file) in _PLUGIN_SPECS.items():
        css_path = os.path.join(vendor, css_file)
        js_path  = os.path.join(vendor, js_file)
        if os.path.exists(css_path) and os.path.exists(js_path):
            with open(css_path, encoding="utf-8") as f:
                css = f.read()
            with open(js_path, encoding="utf-8") as f:
                js = f.read()
            result[name] = (css, js)
    return result
