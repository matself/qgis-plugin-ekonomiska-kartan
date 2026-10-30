"""Map tool to drag a search rectangle (a plain click selects the sheet under it)."""
from qgis.core import Qgis, QgsGeometry, QgsRectangle
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor


def style_band(band, stroke, fill):
    band.setColor(stroke)
    band.setFillColor(fill)
    band.setWidth(2)


class RectTool(QgsMapTool):
    """Emits ``finished(QgsRectangle)`` in map canvas CRS when the mouse is released."""

    finished = pyqtSignal(QgsRectangle)

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._start = None
        self._band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        style_band(self._band, QColor(220, 30, 30), QColor(220, 30, 30, 40))
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
        self._band.reset(Qgis.GeometryType.Polygon)
        self.finished.emit(rect)

    def deactivate(self):
        self._start = None
        self._band.reset(Qgis.GeometryType.Polygon)
        super().deactivate()

    def cleanup(self):
        self._canvas.scene().removeItem(self._band)
        self._band = None
