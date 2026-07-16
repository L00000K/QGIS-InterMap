"""Extract label configuration from QGIS layer labeling settings."""
from typing import Optional

from .compat import _HAS_PAL
from .utils import _color_to_hex, _size_to_px


def _extract_label_config(layer) -> Optional[dict]:
    """Extract label settings from a vector layer. Returns None if no label field is set."""
    if not _HAS_PAL:
        return None
    try:
        if not hasattr(layer, "labeling") or layer.labeling() is None:
            return None
        labeling = layer.labeling()
        if not hasattr(labeling, "settings"):
            return None
        settings = labeling.settings()
        field = settings.fieldName
        if not field:
            return None
        fmt = settings.format()
        font = fmt.font()
        color = fmt.color()
        font_px = max(8, round(_size_to_px(fmt.size(), fmt.sizeUnit())))
        cfg: dict = {
            "field":       field,
            "isExpr":      bool(settings.isExpression),
            "enabled":     bool(layer.labelsEnabled()),
            "fontSize":    font_px,
            "fontColor":   _color_to_hex(color),
            "fontOpacity": round(float(fmt.opacity()), 3),
            "fontFamily":  font.family() or "sans-serif",
            "bold":        bool(font.bold()),
            "italic":      bool(font.italic()),
        }
        buf = fmt.buffer()
        if hasattr(buf, "enabled") and buf.enabled():
            bc = buf.color()
            cfg["bufferSize"]  = max(1, round(_size_to_px(buf.size(), buf.sizeUnit())))
            cfg["bufferColor"] = _color_to_hex(bc)
        # Scale-based label visibility
        if getattr(settings, 'scaleBasedVisibility', False):
            min_sc = getattr(settings, 'minimumScale', 0.0)
            max_sc = getattr(settings, 'maximumScale', 0.0)
            if min_sc > 0:
                cfg["labelScaleMin"] = float(min_sc)  # most-zoomed-in denominator
            if max_sc > 0:
                cfg["labelScaleMax"] = float(max_sc)  # most-zoomed-out denominator
        # Line placement (above / on / below)
        try:
            flags = 0
            if hasattr(settings, 'lineSettings'):
                ls = settings.lineSettings()
                if callable(getattr(ls, 'placementFlags', None)):
                    flags = int(ls.placementFlags())
            if not flags and hasattr(settings, 'placementFlags'):
                flags = int(settings.placementFlags)
            # QgsPalLayerSettings.LinePlacementFlags: OnLine=1, AboveLine=2, BelowLine=4
            if flags & 2:
                cfg["linePlacement"] = "above"
            elif flags & 4:
                cfg["linePlacement"] = "below"
            elif flags & 1:
                cfg["linePlacement"] = "on"
        except Exception:
            pass
        return cfg
    except Exception:
        return None
