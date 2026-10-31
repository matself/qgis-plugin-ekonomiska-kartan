"""Map tool to drag a search rectangle (a plain click selects the sheet under it)."""
from qgis.core import Qgis, QgsGeometry, QgsRectangle
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor


def style_band(band, stroke, fill, width=2):
    band.setColor(stroke)
    band.setFillColor(fill)
    band.setWidth(width)


class RectTool(QgsMapTool):
    """Emits ``finished(QgsRectangle)`` in map canvas CRS when the mouse is released.

    ``modifiers`` holds the keyboard modifiers that were down at that moment.
    """

    finished = pyqtSignal(QgsRectangle)

    def __init__(self, canvas, color=None):
        super().__init__(canvas)
        color = color or QColor(220, 30, 30)
        self._canvas = canvas
        self._start = None
        self.modifiers = Qt.KeyboardModifier.NoModifier
        self._band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        style_band(self._band, color, QColor(color.red(), color.green(), color.blue(), 40))
        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasPressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.mapPoint()

    def canvasMoveEvent(self, event):  # noqa: N802
        if self._start is not None:
            rect = QgsRectangle(self._start, event.mapPoint())
            self._band.setToGeometry(QgsGeometry.fromRect(rect), None)

    def canvasReleaseEvent(self, event):  # noqa: N802
        if self._start is None:
            return
        rect = QgsRectangle(self._start, event.mapPoint())
        self._start = None
        self.modifiers = event.modifiers()
        self._band.reset(Qgis.GeometryType.Polygon)
        self.finished.emit(rect)

    def deactivate(self):
        self._start = None
        self._band.reset(Qgis.GeometryType.Polygon)
        super().deactivate()

    def cleanup(self):
        self._canvas.scene().removeItem(self._band)
        self._band = None
