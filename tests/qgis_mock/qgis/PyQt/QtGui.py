class QColor:
    def __init__(self, r=0, g=0, b=0, a=255):
        self._r, self._g, self._b, self._a = r, g, b, a

    def red(self):
        return self._r

    def green(self):
        return self._g

    def blue(self):
        return self._b

    def alpha(self):
        return self._a

    def alphaF(self):
        return self._a / 255.0

    def name(self):
        return "#{:02x}{:02x}{:02x}".format(self._r, self._g, self._b)

    def isValid(self):
        return True


class QPainter:
    def __init__(self, *args):
        pass

    def end(self):
        pass


class _EnumName(str):
    """Dotted enum name that keeps resolving, for Qt6's scoped enum members
    (QFont.Weight.Bold, QImage.Format.Format_ARGB32)."""
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _EnumName("%s.%s" % (cls, name))


class _EnumMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _EnumName("%s.%s" % (cls.__name__, name))


class QImage(metaclass=_EnumMeta):
    def __init__(self, *args):
        pass


class _Placeholder(metaclass=_EnumMeta):
    def __init__(self, *args, **kwargs):
        pass


_placeholder_cache = {}


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    if name not in _placeholder_cache:
        _placeholder_cache[name] = _EnumMeta(name, (_Placeholder,), {})
    return _placeholder_cache[name]
