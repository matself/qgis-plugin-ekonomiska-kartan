"""Dock widget for Ekonomiska kartan."""
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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

from . import adjust, georef, grid, gridlayer
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
        self.pick_tool = RectTool(self.canvas, QColor(30, 150, 60))
        self.pick_tool.finished.connect(self._on_picked)
        self.pick_tool.deactivated.connect(lambda: self.btn_pick.setChecked(False))
        self.area_band = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        style_band(self.area_band, QColor(220, 30, 30), QColor(220, 30, 30, 30))
        # sheets in the list: grey = listed, green = ticked for download, orange = current row
        self.bands = {
            "listed": QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon),
            "ticked": QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon),
            "current": QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon),
        }
        style_band(self.bands["listed"], QColor(90, 90, 90, 170), QColor(90, 90, 90, 25), 1)
        style_band(self.bands["ticked"], QColor(30, 150, 60), QColor(30, 150, 60, 90))
        style_band(self.bands["current"], QColor(255, 150, 0), QColor(255, 150, 0, 0), 4)
        self.canvas.destinationCrsChanged.connect(self._update_highlight)
        self._grid_following = False  # extentsChanged is connected to the grid timer
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

        self.btn_pick = QPushButton(self.tr("Pick sheets on map"))
        self.btn_pick.setCheckable(True)
        self.btn_pick.setEnabled(False)  # needs a sheet list
        self.btn_pick.setToolTip(
            self.tr(
                "Click a sheet to select or deselect it. Drag a rectangle to select several;"
                " hold Shift to add to the selection or Ctrl to remove from it."
            )
        )
        self.btn_pick.toggled.connect(self._toggle_pick)
        layout.addWidget(self.btn_pick)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Sheet"), self.tr("Edition"), self.tr("Size")])
        self.tree.itemChanged.connect(self._update_total)
        self.tree.itemChanged.connect(self._update_highlight)
        self.tree.currentItemChanged.connect(self._update_highlight)
        self.tree.setMinimumHeight(90)
        self.tree.setMaximumHeight(190)  # about 7 rows, then it scrolls; saves screen space
        layout.addWidget(self.tree)

        row = QHBoxLayout()
        self.lbl_total = QLabel("")
        row.addWidget(self.lbl_total, 1)
        self.btn_all = QPushButton(self.tr("Select all"))
        self.btn_none = QPushButton(self.tr("Select none"))
        self.btn_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.btn_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.btn_all.setEnabled(False)  # both need a sheet list
        self.btn_none.setEnabled(False)
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_none)
        layout.addLayout(row)

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

        layout.addWidget(self._build_adjust_box())

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch(1)
        self.setWidget(content)
        QgsProject.instance().readProject.connect(self.ensure_grid)
        self.ensure_grid()
        self.iface.layerTreeView().currentLayerChanged.connect(self._on_layer_selected)
        self._on_layer_selected(self.iface.activeLayer())

    # -- map: grid and search box ---------------------------------------
    def _toggle_draw(self, on):
        if on:
            self.canvas.setMapTool(self.tool)
        elif self.canvas.mapTool() is self.tool:
            self.canvas.unsetMapTool(self.tool)

    def _toggle_pick(self, on):
        if on:
            self.canvas.setMapTool(self.pick_tool)
        elif self.canvas.mapTool() is self.pick_tool:
            self.canvas.unsetMapTool(self.pick_tool)

    def ensure_grid(self, *_):
        """Add the sheet grid layer to the project and keep it following the map.

        Called when the plugin is opened and when another project is loaded. The layer is
        never removed from here (only on unload): the user hides or removes it in the layer
        list, and a removed layer is not added back until the next call.
        """
        if not self._grid_following:
            self.canvas.extentsChanged.connect(self._grid_timer.start)
            self._grid_following = True
        gridlayer.update_layer(gridlayer.canvas_bbox_3021(self.canvas))

    def _update_grid(self):
        """Timer after the map moved: refresh the grid layer, unless the user removed it."""
        if gridlayer.get_layer() is None:
            self._stop_following_grid()
        else:
            gridlayer.update_layer(gridlayer.canvas_bbox_3021(self.canvas))

    def _stop_following_grid(self):
        if self._grid_following:
            self.canvas.extentsChanged.disconnect(self._grid_timer.start)
            self._grid_following = False

    def _on_rect_drawn(self, rect):
        self.area_band.setToGeometry(QgsGeometry.fromRect(rect), None)
        self._search(gridlayer.rect_to_3021(rect, self.canvas.mapSettings().destinationCrs()))

    def clear_search(self):
        """Remove the search box from the map and empty the sheet list."""
        self._search_id += 1  # a listing still running must not refill the list
        self.area_band.reset(Qgis.GeometryType.Polygon)
        self.btn_pick.setChecked(False)
        self.btn_pick.setEnabled(False)
        self.tree.blockSignals(True)
        self.tree.clear()
        self.tree.blockSignals(False)
        self._update_highlight()
        self._update_total()
        self.lbl_total.setText("")
        self.lbl_status.setText("")
        self.btn_download.setEnabled(False)
        self.btn_extent.setEnabled(True)
        self.btn_draw.setEnabled(True)

    def cleanup(self):
        """Remove everything this widget put on the map (called on plugin unload)."""
        self._stop_following_grid()
        QgsProject.instance().readProject.disconnect(self.ensure_grid)
        self.iface.layerTreeView().currentLayerChanged.disconnect(self._on_layer_selected)
        gridlayer.remove_layer()
        self.canvas.destinationCrsChanged.disconnect(self._update_highlight)
        self.canvas.unsetMapTool(self.tool)
        self.canvas.unsetMapTool(self.pick_tool)
        self.tool.cleanup()
        self.pick_tool.cleanup()
        self.canvas.scene().removeItem(self.area_band)
        for band in self.bands.values():
            self.canvas.scene().removeItem(band)

    # -- map: sheets in the list ----------------------------------------
    def _items(self):
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def _edition(self, item):
        return self.tree.itemWidget(item, 1).currentData()

    def _update_highlight(self, *_):
        """Show the listed sheets on the map: all grey, ticked ones green, current row orange."""
        items = self._items()
        cells = {
            "listed": {c for it in items for c in self._edition(it).covers},
            "ticked": {c for e in self._selected() for c in e.covers},
            "current": set(),
        }
        current = self.tree.currentItem()
        if current is not None and self.tree.indexOfTopLevelItem(current) >= 0:
            cells["current"] = set(self._edition(current).covers)
        crs = self.canvas.mapSettings().destinationCrs()
        for key, band in self.bands.items():
            geometry = gridlayer.cells_geometry(cells[key], crs)
            if geometry is None:
                band.reset(Qgis.GeometryType.Polygon)
            else:
                band.setToGeometry(geometry, None)

    def _on_picked(self, rect):
        """Map click or drag with the pick tool: tick/untick the listed sheets under it.

        A click toggles the sheet (Shift: tick, Ctrl: untick); a drag replaces the selection
        (Shift: add to it, Ctrl: remove from it).
        """
        click = max(rect.width(), rect.height()) < 4 * self.canvas.mapUnitsPerPixel()
        if click:
            centre = rect.center()
            rect = QgsRectangle(centre, centre)
        bbox = gridlayer.rect_to_3021(rect, self.canvas.mapSettings().destinationCrs())
        under = set(
            grid.rutor_in_bbox(
                bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()
            )
        )
        hit = [it for it in self._items() if under.intersection(self._edition(it).covers)]
        if not hit and click:
            return
        mods = self.pick_tool.modifiers
        add = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        remove = bool(mods & Qt.KeyboardModifier.ControlModifier)
        ticked, unticked = Qt.CheckState.Checked, Qt.CheckState.Unchecked
        self.tree.blockSignals(True)
        for item in self._items():
            if item in hit:
                if remove:
                    state = unticked
                elif add:
                    state = ticked
                elif click:
                    state = unticked if item.checkState(0) == ticked else ticked
                else:
                    state = ticked
            elif not (add or remove or click):
                state = unticked  # a plain drag replaces the selection
            else:
                continue
            item.setCheckState(0, state)
        self.tree.blockSignals(False)
        if hit and click:
            self.tree.setCurrentItem(hit[0])
            self.tree.scrollToItem(hit[0])
        self._update_total()
        self._update_highlight()

    def _on_edition_changed(self, item):
        self._refresh_item(item)
        self._update_highlight()

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
            item = QTreeWidgetItem([eds[0].sheet, "", ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            combo = QComboBox()
            for ed in reversed(eds):  # latest first = default
                combo.addItem(ed.label + ("" if "tif" in ed.files else self.tr(" (no tif)")), ed)
            combo.currentIndexChanged.connect(lambda _i, it=item: self._on_edition_changed(it))
            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, 1, combo)
            self._refresh_item(item)
        self.tree.blockSignals(False)
        self.btn_pick.setEnabled(bool(task.editions))
        self._update_highlight()
        if not task.editions:
            self.lbl_status.setText(self.tr("No Ekonomiska kartan sheets found in this area."))
            self._update_total()
            return
        missing = len(set(task.rutor) - task.covered)
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
        listed = self.tree.topLevelItemCount() > 0
        self.btn_all.setEnabled(listed)
        self.btn_none.setEnabled(listed)

    def _set_all(self, state):
        """Tick or untick every sheet in the list."""
        self.tree.blockSignals(True)
        for item in self._items():
            item.setCheckState(0, state)
        self.tree.blockSignals(False)
        self._update_total()
        self._update_highlight()

    # -- adjust the placement of a sheet --------------------------------
    def _build_adjust_box(self):
        """Collapsed section: move the selected sheet layer east/north by a distance in metres."""
        box = QGroupBox(self.tr("Adjust placement"))
        box.setCheckable(True)
        box.setChecked(False)
        box.setToolTip(
            self.tr(
                "Moves the sheet on the map by the given distance (minus = west or south). The"
                " shift is remembered on this computer and used again whenever this plugin"
                " loads the sheet; the downloaded files are not changed."
            )
        )
        outer = QVBoxLayout(box)
        self.adjust_body = QWidget()
        self.adjust_body.setVisible(False)
        box.toggled.connect(self.adjust_body.setVisible)
        body = QVBoxLayout(self.adjust_body)
        body.setContentsMargins(0, 0, 0, 0)

        self.lbl_adjust = QLabel("")
        self.lbl_adjust.setWordWrap(True)
        body.addWidget(self.lbl_adjust)
        form = QFormLayout()
        self.spin_east, self.spin_north = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.spin_east, self.spin_north):
            spin.setRange(-adjust.LIMIT, adjust.LIMIT)
            spin.setDecimals(1)
            spin.setSuffix(" m")
        form.addRow(self.tr("East (+) / west (-):"), self.spin_east)
        form.addRow(self.tr("North (+) / south (-):"), self.spin_north)
        body.addLayout(form)
        row = QHBoxLayout()
        self.btn_adjust = QPushButton(self.tr("Apply"))
        self.btn_adjust.clicked.connect(lambda: self._apply_adjustment(reset=False))
        self.btn_adjust_reset = QPushButton(self.tr("Reset"))
        self.btn_adjust_reset.clicked.connect(lambda: self._apply_adjustment(reset=True))
        row.addWidget(self.btn_adjust)
        row.addWidget(self.btn_adjust_reset)
        body.addLayout(row)
        outer.addWidget(self.adjust_body)
        return box

    def _on_layer_selected(self, layer=None):
        """Follow the layer selected in the layer list: only a sheet of ours can be adjusted."""
        sheet = isinstance(layer, QgsRasterLayer) and adjust.sheet_stem(layer.source())
        self._adjust_layer_id = layer.id() if sheet else None
        if sheet:
            self.lbl_adjust.setText(self.tr("Layer: {name}").format(name=layer.name()))
            dx, dy = adjust.load(QSettings()).get(sheet, (0.0, 0.0))
        else:
            self.lbl_adjust.setText(self.tr("Select a sheet layer in the layer list."))
            dx, dy = 0.0, 0.0
        self.spin_east.setValue(dx)
        self.spin_north.setValue(dy)
        for widget in (self.spin_east, self.spin_north, self.btn_adjust, self.btn_adjust_reset):
            widget.setEnabled(bool(sheet))

    def _apply_adjustment(self, reset):
        layer = QgsProject.instance().mapLayer(self._adjust_layer_id or "")
        if layer is None:
            return
        stem = adjust.sheet_stem(layer.source())
        tif = Path(layer.source().split("|")[0]).with_name(stem + ".tif")
        if not tif.exists():
            self.lbl_status.setText(self.tr("The sheet's tif file is missing next to the layer."))
            return
        dx, dy = (0.0, 0.0) if reset else (self.spin_east.value(), self.spin_north.value())
        try:
            source, _status = adjust.placed_source(tif, (dx, dy))
            layer.setDataSource(source, layer.name(), "gdal")
        except Exception as e:
            error = self.tr("Could not adjust the placement: {error}").format(error=e)
            self.lbl_status.setText(error)
            return
        if not layer.crs().isValid():
            layer.setCrs(QgsCoordinateReferenceSystem(grid.CRS_AUTHID))
        layer.triggerRepaint()
        adjust.store(QSettings(), stem, dx, dy)
        self.spin_east.setValue(dx)
        self.spin_north.setValue(dy)
        if reset:
            text = self.tr("Placement reset: {name}.")
        else:
            text = self.tr("Placement adjusted: {name}.")
        self.lbl_status.setText(text.format(name=layer.name()))

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
        shifts = adjust.load(QSettings())
        self._run(DownloadTask(eds, self.dir_edit.text(), self._on_downloaded, shifts))

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
            if name in task.empty:
                suffix += self.tr(" (empty)")
            if name in task.adjusted:
                suffix += self.tr(" (adjusted)")
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
        if task.empty:
            text += " " + self.tr(
                "Empty image in Lantmäteriet's data (the file holds no picture): {names}."
            ).format(names=", ".join(sorted(task.empty)))
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
