"""A temporary polygon layer that shows the sheet grid for the visible map extent."""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsProject,
    QgsRectangle,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor

from . import grid

LAYER_NAME = "Ekonomiska kartan - grid"
MAX_SHEETS = 1500  # above this the 50 km blocks are shown instead of the 5 km sheets


def _style(layer):
    layer.renderer().setSymbol(
        QgsFillSymbol.createSimple(
            {"color": "0,0,0,0", "outline_color": "30,90,160,255", "outline_width": "0.3"}
        )
    )
    fmt = QgsTextFormat()
    fmt.setSize(9)
    fmt.setColor(QColor(30, 90, 160))
    fmt.buffer().setEnabled(True)
    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    settings.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def canvas_bbox_3021(canvas):
    """Current canvas extent as a QgsRectangle in EPSG:3021."""
    return rect_to_3021(canvas.extent(), canvas.mapSettings().destinationCrs())


def rect_to_3021(rect, src_crs):
    dst = QgsCoordinateReferenceSystem(grid.CRS_AUTHID)
    return QgsCoordinateTransform(src_crs, dst, QgsProject.instance()).transformBoundingBox(rect)


def get_layer():
    layers = QgsProject.instance().mapLayersByName(LAYER_NAME)
    return layers[0] if layers else None


def remove_layer():
    layer = get_layer()
    if layer is not None:
        QgsProject.instance().removeMapLayer(layer.id())


def update_layer(bbox):
    """(Re)build the grid layer for ``bbox`` (EPSG:3021). Returns the layer."""
    layer = get_layer()
    if layer is None:
        layer = QgsVectorLayer(
            f"Polygon?crs={grid.CRS_AUTHID}&field=name:string(10)", LAYER_NAME, "memory"
        )
        _style(layer)
        QgsProject.instance().addMapLayer(layer)

    args = (bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum())
    if grid.count_in_bbox(*args) <= MAX_SHEETS:
        names, bounds = grid.rutor_in_bbox(*args), grid.ruta_bounds
    else:
        names, bounds = grid.storrutor_in_bbox(*args), grid.storruta_bounds

    features = []
    for name in names:
        f = QgsFeature(layer.fields())
        f.setAttribute("name", name)
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(*bounds(name))))
        features.append(f)
    provider = layer.dataProvider()
    provider.truncate()
    provider.addFeatures(features)
    layer.updateExtents()
    layer.triggerRepaint()
    return layer
