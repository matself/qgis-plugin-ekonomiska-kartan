"""Dock widget for Ekonomiska kartan."""
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import georef, grid, gridlayer
from .maptool import RectTool, style_band
from .tasks import DownloadTask, ListTask

EDITION_ROLE = Qt.ItemDataRole.UserRole


def _mb(size):
    return "?" if size is None else f"{size / 1e6:.0f} MB"


class EkonomiskaKartanDockWidget(QDockWidget):
    """Pick an area, choose editions per sheet, download and load the rasters."""

    def __init__(self, iface, parent=None):
        super().__init__("Geodata: Ekonomiska kartan (Lantmäteriet)", parent)
        self.iface = iface
        self.setObjectName("EkonomiskaKartanDockWidget")
        self._tasks = []  # keep Python references alive while running
        self.canvas = iface.mapCanvas()
        self.tool = RectTool(self.canvas)
        self.tool.finished.connect(self._on_rect_drawn)
        self.tool.deactivated.connect(lambda: self.btn_draw.setChecked(False))
        self.area_band = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        style_band(self.area_band, QColor(220, 30, 30), QColor(220, 30, 30, 30))
        self._grid_timer = QTimer(self)
        self._grid_timer.setSingleShot(True)
        self._grid_timer.setInterval(250)
        self._grid_timer.timeout.connect(self._update_grid)

        content = QWidget(self)
        layout = QVBoxLayout(content)

        self.btn_draw = QPushButton("Draw search box on map")
        self.btn_draw.setCheckable(True)
        self.btn_draw.setToolTip("Drag a rectangle, or click to pick a single sheet")
        self.btn_draw.toggled.connect(self._toggle_draw)
        layout.addWidget(self.btn_draw)

        self.btn_extent = QPushButton("Use current map extent")
        self.btn_extent.clicked.connect(self.search_canvas_extent)
        layout.addWidget(self.btn_extent)

        self.chk_grid = QCheckBox("Show sheet grid on map")
        self.chk_grid.toggled.connect(self._toggle_grid)
        layout.addWidget(self.chk_grid)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Sheet", "Edition", "Size"])
        self.tree.itemChanged.connect(self._update_total)
        layout.addWidget(self.tree)

        self.lbl_total = QLabel("")
        layout.addWidget(self.lbl_total)

        row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("Download folder")
        btn_dir = QPushButton("…")
        btn_dir.clicked.connect(self._choose_dir)
        row.addWidget(self.dir_edit)
        row.addWidget(btn_dir)
        layout.addLayout(row)

        self.btn_download = QPushButton("Download and load")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.download)
        layout.addWidget(self.btn_download)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        self.setWidget(content)

    # -- map: grid and search box ---------------------------------------
    def _toggle_draw(self, on):
        if on:
            self.canvas.setMapTool(self.tool)
        elif self.canvas.mapTool() is self.tool:
            self.canvas.unsetMapTool(self.tool)

    def _toggle_grid(self, on):
        if on:
            self.canvas.extentsChanged.connect(self._grid_timer.start)
            self._update_grid()
        else:
            self.canvas.extentsChanged.disconnect(self._grid_timer.start)
            gridlayer.remove_layer()

    def _update_grid(self):
        gridlayer.update_layer(gridlayer.canvas_bbox_3021(self.canvas))

    def _on_rect_drawn(self, rect):
        self.area_band.setToGeometry(QgsGeometry.fromRect(rect), None)
        self._search(gridlayer.rect_to_3021(rect, self.canvas.mapSettings().destinationCrs()))

    def cleanup(self):
        """Remove everything this widget put on the map (called on plugin unload)."""
        if self.chk_grid.isChecked():
            self.chk_grid.setChecked(False)
        self.canvas.unsetMapTool(self.tool)
        self.tool.cleanup()
        self.canvas.scene().removeItem(self.area_band)

    # -- search ---------------------------------------------------------
    def search_canvas_extent(self):
        rect = self.canvas.extent()
        self.area_band.setToGeometry(QgsGeometry.fromRect(rect), None)
        self._search(gridlayer.canvas_bbox_3021(self.canvas))

    def _search(self, bbox):
        rutor = grid.rutor_in_bbox(
            bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()
        )
        if not rutor:
            self.lbl_status.setText("The area is outside the Ekonomiska kartan grid.")
            return
        if len(rutor) > 100:
            self.lbl_status.setText(f"{len(rutor)} sheets - choose a smaller area (max 100).")
            return
        self.lbl_status.setText(f"Listing {len(rutor)} sheets …")
        self.btn_extent.setEnabled(False)
        self.btn_draw.setEnabled(False)
        self._run(ListTask(rutor, self._on_listed))

    def _on_listed(self, task, ok):
        self.btn_extent.setEnabled(True)
        self.btn_draw.setEnabled(True)
        if not ok:
            self.lbl_status.setText(f"Listing failed: {task.error or 'cancelled'}")
            return
        self.tree.blockSignals(True)
        self.tree.clear()
        for ruta in sorted(task.editions):
            eds = task.editions[ruta]
            item = QTreeWidgetItem([ruta, "", ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            combo = QComboBox()
            for ed in reversed(eds):  # latest first = default
                combo.addItem(ed.label + ("" if "tif" in ed.files else " (no tif)"), ed)
            combo.currentIndexChanged.connect(lambda _i, it=item: self._refresh_item(it))
            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, 1, combo)
            self._refresh_item(item)
        self.tree.blockSignals(False)
        missing = len(task.rutor) - len(task.editions)
        text = f"{len(task.editions)} sheets available"
        if missing:
            text += f", {missing} without map"
        self.lbl_status.setText(text)
        self._update_total()

    def _refresh_item(self, item):
        ed = self.tree.itemWidget(item, 1).currentData()
        listed = georef.is_listed(ed.stem)
        item.setText(2, _mb(ed.tif_size) + (" ⚠" if listed else ""))
        tip = "Map larger than its grid cell; georeferencing repaired on load"
        item.setToolTip(2, tip if listed else "")
        self._update_total()

    def _selected(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                ed = self.tree.itemWidget(item, 1).currentData()
                if "tif" in ed.files:
                    out.append(ed)
        return out

    def _update_total(self, *_):
        eds = self._selected()
        total = sum(e.tif_size or 0 for e in eds)
        self.lbl_total.setText(f"{len(eds)} sheets selected, about {_mb(total)}")
        self.btn_download.setEnabled(bool(eds))

    # -- download -------------------------------------------------------
    def _choose_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def download(self):
        if not self.dir_edit.text():
            self._choose_dir()
        if not self.dir_edit.text():
            return
        self.btn_download.setEnabled(False)
        self.lbl_status.setText("Downloading …")
        self._run(DownloadTask(self._selected(), self.dir_edit.text(), self._on_downloaded))

    def _on_downloaded(self, task, ok):
        self.btn_download.setEnabled(True)
        if not ok:
            self.lbl_status.setText(f"Download failed: {task.error or 'cancelled'}")
            return
        root = QgsProject.instance().layerTreeRoot()
        group = root.addGroup("Ekonomiska kartan")
        crs = QgsCoordinateReferenceSystem(grid.CRS_AUTHID)
        loaded, repaired, unverified = 0, 0, []
        for name, path, status in task.layers:
            suffix = " (unverified)" if status == georef.UNVERIFIED else ""
            layer = QgsRasterLayer(path, name + suffix)
            if not layer.isValid():
                continue
            if not layer.crs().isValid():
                layer.setCrs(crs)
            QgsProject.instance().addMapLayer(layer, False)
            group.addLayer(layer)
            loaded += 1
            if status:
                repaired += 1
            if status == georef.UNVERIFIED:
                unverified.append(name)
        text = f"Loaded {loaded} sheets."
        if repaired:
            text += (
                f" {repaired} were larger than their grid cell (wrong .tfw/.TAB); placement"
                " repaired in a _fixed.vrt next to the tif."
            )
        if unverified:
            text += (
                f" Placement uncertain, please check against a base map: {', '.join(unverified)}."
            )
        self.lbl_status.setText(text)

    def _run(self, task):
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)
