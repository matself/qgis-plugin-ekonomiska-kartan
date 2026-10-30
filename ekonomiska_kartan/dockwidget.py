"""Dock widget for Ekonomiska kartan."""
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
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

from . import grid
from .tasks import DownloadTask, ListTask

EDITION_ROLE = Qt.ItemDataRole.UserRole


def _mb(size):
    return "?" if size is None else f"{size / 1e6:.0f} MB"


class EkonomiskaKartanDockWidget(QDockWidget):
    """Pick an area, choose editions per sheet, download and load the rasters."""

    def __init__(self, iface, parent=None):
        super().__init__("Ekonomiska kartan", parent)
        self.iface = iface
        self.setObjectName("EkonomiskaKartanDockWidget")
        self._tasks = []  # keep Python references alive while running

        content = QWidget(self)
        layout = QVBoxLayout(content)

        self.btn_extent = QPushButton("Use current map extent")
        self.btn_extent.clicked.connect(self.search_canvas_extent)
        layout.addWidget(self.btn_extent)

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

    # -- search ---------------------------------------------------------
    def search_canvas_extent(self):
        canvas = self.iface.mapCanvas()
        src = canvas.mapSettings().destinationCrs()
        dst = QgsCoordinateReferenceSystem(grid.CRS_AUTHID)
        rect = QgsCoordinateTransform(src, dst, QgsProject.instance()).transformBoundingBox(
            canvas.extent()
        )
        rutor = grid.rutor_in_bbox(
            rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()
        )
        if len(rutor) > 100:
            self.lbl_status.setText(f"{len(rutor)} sheets - zoom in first (max 100).")
            return
        self.lbl_status.setText(f"Listing {len(rutor)} sheets …")
        self.btn_extent.setEnabled(False)
        task = ListTask(rutor, self._on_listed)
        self._run(task)

    def _on_listed(self, task, ok):
        self.btn_extent.setEnabled(True)
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
        item.setText(2, _mb(ed.tif_size))
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
        for path in task.tifs:
            layer = QgsRasterLayer(path, path.replace("\\", "/").rsplit("/", 1)[-1])
            if not layer.isValid():
                continue
            if not layer.crs().isValid():
                layer.setCrs(crs)
            QgsProject.instance().addMapLayer(layer, False)
            group.addLayer(layer)
        self.lbl_status.setText(f"Loaded {len(task.tifs)} sheets.")

    def _run(self, task):
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)
