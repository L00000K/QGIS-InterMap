"""QGIS version gate: warn when running on a release older than the last LTR."""
from qgis.PyQt.QtCore import QSettings

from .dialog.constants import _SETTINGS_KEY

# Minimum QGIS we support, in QGIS integer format (3.46.0 -> 34600).
# Tracks the current Long Term Release (QGIS ships an LTR each February).
# BUMP THIS when a new LTR ships.
_MIN_QGIS_VERSION_INT = 34600
_MIN_QGIS_VERSION_STR = "3.46 LTR"

_SUPPRESS_KEY = f"{_SETTINGS_KEY}/suppress_version_warning"

# Set once the warning has been shown, so it appears at most once per session.
_warned_this_session = False


def _qgis_version_int():
    """Running QGIS version as an int, or None if it cannot be determined."""
    try:
        from qgis.core import Qgis
    except Exception:
        return None
    try:
        return int(Qgis.QGIS_VERSION_INT)
    except Exception:
        pass
    try:
        return int(Qgis.versionInt())
    except Exception:
        pass
    try:
        # Last resort: parse "3.46.2-Firenze" style strings.
        parts = str(Qgis.QGIS_VERSION).split("-")[0].split(".")
        major, minor = int(parts[0]), int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major * 10000 + minor * 100 + patch
    except Exception:
        return None


def _version_text(vint):
    return "{}.{}.{}".format(vint // 10000, (vint // 100) % 100, vint % 100)


def warn_if_unsupported(iface):
    """Warn once if QGIS is older than the last LTR. Never raises."""
    global _warned_this_session
    try:
        if _warned_this_session:
            return
        if QSettings().value(_SUPPRESS_KEY, False, type=bool):
            return

        vint = _qgis_version_int()
        if vint is None or vint >= _MIN_QGIS_VERSION_INT:
            return

        _warned_this_session = True
        msg = (
            "InterMap supports QGIS {} and newer — you are running {}. "
            "Exports may render incorrectly (symbol sizes and units in "
            "particular). You can continue, but please update QGIS."
        ).format(_MIN_QGIS_VERSION_STR, _version_text(vint))

        try:
            from qgis.core import Qgis
            iface.messageBar().pushMessage("InterMap", msg, level=Qgis.Warning, duration=15)
            return
        except Exception:
            pass

        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.warning(iface.mainWindow(), "InterMap — unsupported QGIS version", msg)
    except Exception:
        # A version check must never stop the plugin from opening.
        pass
