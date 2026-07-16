"""Small shared helpers: rich-text handling, colours, unit conversion."""
from qgis.PyQt.QtGui import QColor

try:
    from qgis.core import QgsUnitTypes
except ImportError:  # pragma: no cover
    QgsUnitTypes = None


def _richtext_body(html):
    """Extract inner body from Qt rich-text HTML; fall back to html.escape for plain text."""
    import re
    import html as _h
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if m:
        body = m.group(1).strip()
        # Strip all style attributes from <p> tags — Qt embeds margin/spacing rules
        # that cause excessive vertical gaps in browsers. Bold/italic live on <span>s.
        body = re.sub(r'<p\s+style="[^"]*"', '<p', body)
        return body
    return _h.escape(html)


def _color_to_hex(color: QColor) -> str:
    return "#{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue())


def _color_to_rgba(color: QColor) -> str:
    return "rgba({},{},{},{:.3f})".format(
        color.red(), color.green(), color.blue(), color.alphaF()
    )


def _size_to_px(size: float, unit) -> float:
    """Convert a QGIS symbol size in its render unit to approximate pixels (96 DPI)."""
    try:
        if unit == QgsUnitTypes.RenderPixels:
            return size
        if unit == QgsUnitTypes.RenderPoints:
            return size * 96.0 / 72.0
        if unit == QgsUnitTypes.RenderInches:
            return size * 96.0
        # Millimeters (QGIS default) and everything else
        return size * 96.0 / 25.4
    except Exception:
        # Fallback assuming millimeters
        return size * 96.0 / 25.4
