"""Auto-stubbing QtWidgets replacement — every widget class is a placeholder
that accepts any constructor arguments and supports subclassing."""


class _NoOp:
    """Callable that swallows everything: any call returns another _NoOp and
    any attribute (e.g. a signal's .connect) is another _NoOp — so chained UI
    wiring like `btn.clicked.connect(...)` runs harmlessly headless. Comparisons
    behave like a 'not found' index (-1) so combo.findData(...) >= 0 is False."""
    def __call__(self, *args, **kwargs):
        return _NoOp()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _NoOp()

    def __int__(self): return -1
    def __index__(self): return -1
    def __ge__(self, o): return False
    def __gt__(self, o): return False
    def __le__(self, o): return True
    def __lt__(self, o): return True
    def __eq__(self, o): return False
    def __hash__(self): return 0
    def __bool__(self): return False


_noop = _NoOp()


class _PlaceholderMeta(type):
    # Class-level attribute access (enum constants like QScrollArea.NoFrame,
    # QAbstractItemView.SelectRows) returns a unique placeholder value.
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return "%s.%s" % (cls.__name__, name)


class _Placeholder(metaclass=_PlaceholderMeta):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        # Any method call on a widget stub is a harmless no-op, so UI-building
        # code (setWidgetResizable, addWidget, setLayout, …) can run headless.
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
