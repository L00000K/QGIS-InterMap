"""Auto-stubbing QtWidgets replacement — every widget class is a placeholder
that accepts any constructor arguments and supports subclassing."""


class _Placeholder:
    def __init__(self, *args, **kwargs):
        pass


_placeholder_cache = {}


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    if name not in _placeholder_cache:
        _placeholder_cache[name] = type(name, (_Placeholder,), {})
    return _placeholder_cache[name]
