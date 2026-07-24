"""Auto-stubbing qgis.core replacement (see package docstring)."""


class _AutoAttr:
    """Instances hand out unique, hashable placeholder constants per name."""

    def __init__(self, prefix):
        self._prefix = prefix
        self._cache = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self._cache.setdefault(name, f"{self._prefix}.{name}")


class QgsCoordinateReferenceSystem:
    def __init__(self, authid=""):
        self._authid = authid

    def authid(self):
        return self._authid

    def isValid(self):
        return True


class QgsMapLayer:
    VectorLayer = 0
    RasterLayer = 1


class QgsSymbol:
    # Geometry types, matching QGIS
    Marker = 0
    Line = 1
    Fill = 2


class _StubMapThemeCollection:
    def mapThemes(self):
        return []

    def mapThemeVisibleLayers(self, _name):
        return []


class _StubRoot:
    def children(self):
        return []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: []


class _StubProject:
    def mapLayer(self, _layer_id):
        return None

    def mapLayers(self):
        return {}

    def mapThemeCollection(self):
        return _StubMapThemeCollection()

    def layerTreeRoot(self):
        return _StubRoot()

    def transformContext(self):
        return None

    def __getattr__(self, name):
        # Anything else the dialog asks of the project is a harmless no-op,
        # so the whole UI can be built headless for smoke tests.
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


class QgsProject:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = _StubProject()
        return cls._instance


class QgsUnitTypes:
    RenderMillimeters = "unit.mm"
    RenderPixels = "unit.px"
    RenderPoints = "unit.pt"
    RenderInches = "unit.in"
    RenderMapUnits = "unit.mapunits"


class QgsWkbTypes:
    PointGeometry = 0
    LineGeometry = 1
    PolygonGeometry = 2

    @staticmethod
    def geometryType(_wkb):
        return QgsWkbTypes.PointGeometry


class _Placeholder:
    """Generic placeholder class; supports isinstance checks and construction."""

    def __init__(self, *args, **kwargs):
        pass


_placeholder_cache = {}


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    if name not in _placeholder_cache:
        _placeholder_cache[name] = type(name, (_Placeholder,), {})
    return _placeholder_cache[name]
