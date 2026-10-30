"""Dock widget for Ekonomiska kartan."""
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
LARGE_DOWNLOAD = 50  # sheets; ask for confirmation from this many selected sheets
PLACEMENT_KEY = "ekonomiska_kartan/placement"
TOP, ABOVE_SELECTED, BOTTOM = "top", "selected", "bottom"


def _mb(size):
    return "?" if size is None else f"{size / 1e6:.0f} MB"


class EkonomiskaKartanDockWidget(QDockWidget):
    """Pick an area, choose editions per sheet, download and load the rasters."""

    def tr(self, text):
        # fixed context: QObject.tr would use the Python class name only on some PyQt builds
        return QCoreApplication.translate("EkonomiskaKartanDockWidget", text)

    def __init__(self, iface, parent=None):
        super().__init__("Geodata: Ekonomiska kartan (Lantmäteriet)", parent)
        self.iface = iface
        self.setObjectName("EkonomiskaKartanDockWidget")
        self._tasks = []  # keep Python references alive while running
        self._search_id = 0  # bumped by every search and by clear, to drop stale list results
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

        self.btn_draw = QPushButton(self.tr("Draw search box on map"))
        self.btn_draw.setCheckable(True)
        self.btn_draw.setToolTip(self.tr("Drag a rectangle, or click to pick a single sheet"))
        self.btn_draw.toggled.connect(self._toggle_draw)
        layout.addWidget(self.btn_draw)

        self.btn_extent = QPushButton(self.tr("Use current map extent"))
        self.btn_extent.clicked.connect(self.search_canvas_extent)
        layout.addWidget(self.btn_extent)

        self.btn_clear = QPushButton(self.tr("Clear search box"))
        self.btn_clear.setToolTip(
            self.tr("Remove the search box from the map and empty the sheet list")
        )
        self.btn_clear.clicked.connect(self.clear_search)
        layout.addWidget(self.btn_clear)

        self.chk_grid = QCheckBox(self.tr("Show sheet grid on map"))
        self.chk_grid.toggled.connect(self._toggle_grid)
        layout.addWidget(self.chk_grid)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Sheet"), self.tr("Edition"), self.tr("Size")])
        self.tree.itemChanged.connect(self._update_total)
        self.tree.setMinimumHeight(90)
        self.tree.setMaximumHeight(190)  # about 7 rows, then it scrolls; saves screen space
        layout.addWidget(self.tree)

        self.lbl_total = QLabel("")
        layout.addWidget(self.lbl_total)

        row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText(self.tr("Download folder"))
        btn_dir = QPushButton("…")
        btn_dir.clicked.connect(self._choose_dir)
        row.addWidget(self.dir_edit)
        row.addWidget(btn_dir)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Add to layer list:")))
        self.cmb_place = QComboBox()
        self.cmb_place.addItem(self.tr("At the top"), TOP)
        self.cmb_place.addItem(self.tr("Above the selected layer"), ABOVE_SELECTED)
        self.cmb_place.addItem(self.tr("At the bottom"), BOTTOM)
        saved = self.cmb_place.findData(QSettings().value(PLACEMENT_KEY, TOP))
        self.cmb_place.setCurrentIndex(max(saved, 0))
        self.cmb_place.currentIndexChanged.connect(
            lambda _i: QSettings().setValue(PLACEMENT_KEY, self.cmb_place.currentData())
        )
        row.addWidget(self.cmb_place, 1)
        layout.addLayout(row)

        self.btn_download = QPushButton(self.tr("Download and load"))
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.download)
        layout.addWidget(self.btn_download)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch(1)
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

    def clear_search(self):
        """Remove the search box from the map and empty the sheet list."""
        self._search_id += 1  # a listing still running must not refill the list
        self.area_band.reset(Qgis.GeometryType.Polygon)
        self.tree.clear()
        self.lbl_total.setText("")
        self.lbl_status.setText("")
        self.btn_download.setEnabled(False)
        self.btn_extent.setEnabled(True)
        self.btn_draw.setEnabled(True)

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
            self.lbl_status.setText(self.tr("The area is outside the Ekonomiska kartan grid."))
            return
        if len(rutor) > 100:
            text = self.tr("{count} sheets - choose a smaller area (max 100).")
            self.lbl_status.setText(text.format(count=len(rutor)))
            return
        self.lbl_status.setText(self.tr("Listing {count} sheets …").format(count=len(rutor)))
        self.btn_extent.setEnabled(False)
        self.btn_draw.setEnabled(False)
        self._search_id += 1
        search_id = self._search_id
        self._run(ListTask(rutor, lambda task, ok: self._on_listed(task, ok, search_id)))

    def _on_listed(self, task, ok, search_id):
        if search_id != self._search_id:  # cleared or replaced while listing
            return
        self.btn_extent.setEnabled(True)
        self.btn_draw.setEnabled(True)
        if not ok:
            error = task.error or self.tr("cancelled")
            self.lbl_status.setText(self.tr("Listing failed: {error}").format(error=error))
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
                combo.addItem(ed.label + ("" if "tif" in ed.files else self.tr(" (no tif)")), ed)
            combo.currentIndexChanged.connect(lambda _i, it=item: self._refresh_item(it))
            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, 1, combo)
            self._refresh_item(item)
        self.tree.blockSignals(False)
        if not task.editions:
            self.lbl_status.setText(self.tr("No Ekonomiska kartan sheets found in this area."))
            self._update_total()
            return
        missing = len(task.rutor) - len(task.editions)
        text = self.tr("Available sheets: {count}").format(count=len(task.editions))
        if missing:
            text += ". " + self.tr("Sheets without map: {count}").format(count=missing)
        self.lbl_status.setText(text)
        self._update_total()

    def _refresh_item(self, item):
        ed = self.tree.itemWidget(item, 1).currentData()
        listed = georef.is_listed(ed.stem)
        item.setText(2, _mb(ed.tif_size) + (" ⚠" if listed else ""))
        tip = self.tr("Map larger than its grid cell; georeferencing repaired on load")
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
        text = self.tr("Selected sheets: {count}, about {size}")
        self.lbl_total.setText(text.format(count=len(eds), size=_mb(total)))
        self.btn_download.setEnabled(bool(eds))

    # -- download -------------------------------------------------------
    def _choose_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Download folder"), self.dir_edit.text()
        )
        if path:
            self.dir_edit.setText(path)

    def download(self):
        if not self.dir_edit.text():
            self._choose_dir()
        if not self.dir_edit.text():
            return
        eds = self._selected()
        if len(eds) >= LARGE_DOWNLOAD and not self._confirm_large(eds):
            return
        self.btn_download.setEnabled(False)
        self.lbl_status.setText(self.tr("Downloading …"))
        self._run(DownloadTask(eds, self.dir_edit.text(), self._on_downloaded))

    def _confirm_large(self, eds):
        text = self.tr("You are about to download {count} sheets, about {size}. Continue?")
        size = _mb(sum(e.tif_size or 0 for e in eds))
        answer = QMessageBox.question(
            self,
            self.tr("Large download"),
            text.format(count=len(eds), size=size),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_downloaded(self, task, ok):
        self.btn_download.setEnabled(True)
        if not ok:
            error = task.error or self.tr("cancelled")
            self.lbl_status.setText(self.tr("Download failed: {error}").format(error=error))
            return
        group = self._new_group("Ekonomiska kartan")
        crs = QgsCoordinateReferenceSystem(grid.CRS_AUTHID)
        loaded, repaired, unverified = 0, 0, []
        for name, path, status in task.layers:
            suffix = self.tr(" (unverified)") if status == georef.UNVERIFIED else ""
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
        text = self.tr("Loaded sheets: {count}.").format(count=loaded)
        if repaired:
            text += " " + self.tr(
                "{count} were larger than their grid cell (wrong .tfw/.TAB); placement"
                " repaired in a _fixed.vrt next to the tif, the extra map area is kept."
            ).format(count=repaired)
        if unverified:
            text += " " + self.tr(
                "Placement uncertain, please check against a base map: {names}."
            ).format(names=", ".join(unverified))
        self.lbl_status.setText(text)

    def _new_group(self, name):
        """A new layer group at the place chosen in the panel."""
        root = QgsProject.instance().layerTreeRoot()
        place = self.cmb_place.currentData()
        if place == BOTTOM:
            return root.addGroup(name)
        parent, index = root, 0
        if place == ABOVE_SELECTED:
            node = self.iface.layerTreeView().currentNode()
            if node is not None and node.parent() is not None:
                parent = node.parent()
                index = parent.children().index(node)
        children = parent.children()
        # keep the sheet grid (a thin outline layer) on top of the maps
        grid_layer = gridlayer.get_layer()
        if (
            parent is root
            and index == 0
            and children
            and isinstance(children[0], QgsLayerTreeLayer)
            and grid_layer is not None
            and children[0].layerId() == grid_layer.id()
        ):
            index = 1
        return parent.insertGroup(index, name)

    def _run(self, task):
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)
