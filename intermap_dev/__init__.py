def classFactory(iface):
    from .plugin import DevReloadPlugin
    return DevReloadPlugin(iface)
