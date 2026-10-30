"""Ekonomiska kartan - QGIS plugin entry point."""


def classFactory(iface):  # noqa: N802 (name required by QGIS)
    """Load the plugin class. Called by QGIS."""
    from .plugin import EkonomiskaKartanPlugin

    return EkonomiskaKartanPlugin(iface)
