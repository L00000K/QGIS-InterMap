class _QtName(str):
    """A dotted Qt name that keeps resolving.

    Qt6 requires fully-scoped enum members (Qt.CheckState.Checked), so the
    stub has to allow another attribute hop after the enum class. The value is
    still a plain string, so identity comparisons in the code under test work
    exactly as they did.
    """
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _QtName("%s.%s" % (self, name))


class _QtNamespace:
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _QtName("Qt.%s" % name)


Qt = _QtNamespace()


class QSize:
    def __init__(self, w=0, h=0):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h


class QPointF:
    def __init__(self, x=0.0, y=0.0):
        self._x, self._y = x, y


class QRectF:
    def __init__(self, *args):
        self._args = args


class QUrl:
    def __init__(self, url=""):
        self._url = url

    def toString(self):
        return self._url


class QByteArray:
    def __init__(self, data=b""):
        self._data = bytes(data)

    def data(self):
        return self._data


class QBuffer:
    def __init__(self, ba=None):
        self._ba = ba

    def open(self, *_):
        return True

    def close(self):
        pass


def pyqtSignal(*_args, **_kwargs):
    class _Signal:
        def connect(self, *_a):
            pass

        def emit(self, *_a):
            pass

    return _Signal()


class _NoOpCallable:
    """Callable placeholder that also keeps resolving attributes, so both
    QStandardPaths.writableLocation(...) and Qt6's scoped
    QStandardPaths.StandardLocation.DownloadLocation work on the stub."""
    def __call__(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _NoOpCallable()


_noop = _NoOpCallable()


class _PlaceholderMeta(type):
    # Class-level constants/methods (QStandardPaths.DownloadLocation,
    # .writableLocation, …) resolve to placeholders so headless UI build works.
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _noop


class _Placeholder(metaclass=_PlaceholderMeta):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _noop


_placeholder_cache = {}


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    if name not in _placeholder_cache:
        _placeholder_cache[name] = _PlaceholderMeta(name, (_Placeholder,), {})
    return _placeholder_cache[name]
