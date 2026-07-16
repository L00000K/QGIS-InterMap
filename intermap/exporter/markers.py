"""Marker shape encoding and QGIS symbol → inline SVG rendering."""
from qgis.core import QgsSymbol

from .compat import _QgsSimpleMarkerBase
from .utils import _size_to_px


# Map QGIS marker shape names to a small set the web map can draw.
_SHAPE_ALIASES = {
    "square": "square",
    "rectangle": "square",
    "square_with_corners": "square",
    "rounded_square": "square",
    "diamond": "diamond",
    "triangle": "triangle",
    "equilateral_triangle": "triangle",
    "star": "star",
    "regular_star": "star",
    "pentagon": "pentagon",
    "hexagon": "hexagon",
    "octagon": "octagon",
    "cross": "cross",
    "cross2": "x",
    "x": "x",
    "cross_fill": "square",
    "circle": "circle",
}


def _encode_marker_shape(sl) -> str:
    """Return a normalized shape name string for a simple marker symbol layer."""
    try:
        if _QgsSimpleMarkerBase is None:
            return "circle"
        raw = _QgsSimpleMarkerBase.encodeShape(sl.shape())
        return _SHAPE_ALIASES.get(str(raw).lower(), "circle")
    except Exception:
        return "circle"


_svg_id_counter = [0]


def _svg_inner(svg_text: str) -> str:
    """Return the markup between the outer <svg …> and </svg>, or '' on failure."""
    try:
        lt = svg_text.index("<svg")
        gt = svg_text.index(">", lt) + 1
        end = svg_text.rindex("</svg>")
        return svg_text[gt:end].strip()
    except Exception:
        return ""


def _uniquify_svg_ids(inner: str) -> str:
    """Namespace element ids so multiple inlined symbol SVGs can't collide."""
    import re
    ids = set(re.findall(r'id="([^"]+)"', inner))
    if not ids:
        return inner
    _svg_id_counter[0] += 1
    prefix = "s%d_" % _svg_id_counter[0]
    for i in sorted(ids, key=len, reverse=True):
        inner = inner.replace('id="%s"' % i, 'id="%s%s"' % (prefix, i))
        inner = inner.replace('url(#%s)' % i, 'url(#%s%s)' % (prefix, i))
        inner = inner.replace('"#%s"' % i, '"#%s%s"' % (prefix, i))
        inner = inner.replace("'#%s'" % i, "'#%s%s'" % (prefix, i))
    return inner


def _render_marker_symbol_to_svg(symbol, dpi: float = 96.0):
    """
    Render a QGIS marker symbol to an inline SVG fragment, capturing the full
    symbol exactly as QGIS draws it (multi-layer, SVG/font markers, effects).

    Returns {w, h, ax, ay, vw, vh, inner} where w/h/ax/ay are CSS pixels and
    vw/vh are the SVG viewBox dimensions (2× for HiDPI clarity). Returns None
    on failure — in which case the caller's primitive marker style is used.
    """
    if symbol is None:
        return None
    try:
        if symbol.type() != QgsSymbol.Marker:
            return None
    except Exception:
        return None
    try:
        import math as _math
        from qgis.PyQt.QtSvg import QSvgGenerator
        from qgis.PyQt.QtCore import QBuffer, QByteArray, QPointF, QSize, QRectF
        from qgis.PyQt.QtGui import QPainter, QImage
        from qgis.core import QgsRenderContext
    except Exception:
        return None

    # Render at 2× DPI so any rasterized effects look crisp on HiDPI screens.
    # The CSS display size is halved so the visual marker size stays the same.
    OVER = 2
    render_dpi = dpi * OVER

    def _ctx(painter):
        ctx = QgsRenderContext()
        ctx.setPainter(painter)
        try:
            ctx.setScaleFactor(render_dpi / 25.4)
        except Exception:
            pass
        return ctx

    # 1) Measure the symbol's bounds at 2× DPI
    rect = None
    probe_painter = None
    try:
        probe = QImage(32, 32, QImage.Format_ARGB32)
        probe_painter = QPainter(probe)
        rect = symbol.bounds(QPointF(0.0, 0.0), _ctx(probe_painter))
    except Exception:
        rect = None
    finally:
        if probe_painter is not None:
            try:
                probe_painter.end()
            except Exception:
                pass

    pad_css = 2.0
    pad_svg = pad_css * OVER
    if rect is not None and rect.width() > 0 and rect.height() > 0:
        w_svg = rect.width() + 2 * pad_svg
        h_svg = rect.height() + 2 * pad_svg
        ax_svg = -rect.left() + pad_svg
        ay_svg = -rect.top() + pad_svg
    else:
        try:
            s = _size_to_px(symbol.size(), symbol.sizeUnit())
        except Exception:
            s = 12.0
        w_svg = h_svg = (max(6.0, s) + 2 * pad_css) * OVER
        ax_svg = ay_svg = w_svg / 2.0

    w_css = w_svg / OVER
    h_css = h_svg / OVER
    ax_css = ax_svg / OVER
    ay_css = ay_svg / OVER

    # 2) Paint the symbol onto a QSvgGenerator at 2× DPI
    painter = None
    try:
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QBuffer.WriteOnly)
        gen = QSvgGenerator()
        gen.setOutputDevice(dev)
        gen.setResolution(int(render_dpi))
        gen.setSize(QSize(int(_math.ceil(w_svg)), int(_math.ceil(h_svg))))
        gen.setViewBox(QRectF(0.0, 0.0, w_svg, h_svg))
        painter = QPainter()
        if not painter.begin(gen):
            return None
        ctx = _ctx(painter)
        painter.translate(ax_svg, ay_svg)
        symbol.startRender(ctx)
        symbol.renderPoint(QPointF(0.0, 0.0), None, ctx)
        symbol.stopRender(ctx)
        painter.end()
        painter = None
        dev.close()
        svg_text = bytes(buf).decode("utf-8", "replace")
    except Exception:
        if painter is not None:
            try:
                painter.end()
            except Exception:
                pass
        return None

    inner = _uniquify_svg_ids(_svg_inner(svg_text))
    if not inner:
        return None
    return {
        "w": round(w_css, 1), "h": round(h_css, 1),
        "ax": round(ax_css, 1), "ay": round(ay_css, 1),
        "vw": round(w_svg, 1), "vh": round(h_svg, 1),
        "inner": inner,
    }
