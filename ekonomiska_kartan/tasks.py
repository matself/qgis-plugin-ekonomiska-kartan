"""Background tasks: list FTP blocks and download chosen editions."""
from pathlib import Path

from qgis.core import QgsTask
from qgis.PyQt.QtCore import QCoreApplication

from . import adjust, ftpindex, grid, tiffcheck


class ListTask(QgsTask):
    """LIST each needed block directory and collect the editions per sheet."""

    def __init__(self, rutor, on_done):
        super().__init__(
            QCoreApplication.translate("tasks", "Ekonomiska kartan: list available sheets"),
            QgsTask.Flag.CanCancel,
        )
        self.rutor = list(rutor)
        self.on_done = on_done
        self.editions = {}  # first cell -> [Edition]; a sheet over several cells appears once
        self.covered = set()  # the searched cells that have a map
        self.error = None

    def run(self):
        blocks = ftpindex.directories_for(grid.storrutor(self.rutor))
        wanted = set(self.rutor)
        try:
            ftp = ftpindex.connect()
            try:
                for i, block in enumerate(blocks):
                    if self.isCanceled():
                        return False
                    chosen, covered = ftpindex.select_editions(
                        ftpindex.list_block(ftp, block), wanted
                    )
                    for ruta, eds in chosen.items():
                        known = self.editions.setdefault(ruta, [])
                        known.extend(e for e in eds if e.stem not in {k.stem for k in known})
                    self.covered |= covered
                    self.setProgress(100 * (i + 1) / len(blocks))
            finally:
                ftp.close()
        except OSError as e:
            self.error = str(e)
            return False
        except Exception as e:  # ftplib.Error and friends
            self.error = str(e)
            return False
        return True

    def finished(self, result):
        self.on_done(self, result)


class DownloadTask(QgsTask):
    """Download .tif/.tfw/.TAB for the chosen editions; skips existing files."""

    def __init__(self, editions, target_dir, on_done, shifts=None):
        super().__init__(
            QCoreApplication.translate("tasks", "Ekonomiska kartan: download"),
            QgsTask.Flag.CanCancel,
        )
        self.editions = list(editions)
        self.target_dir = Path(target_dir)
        self.on_done = on_done
        self.shifts = shifts or {}  # stem -> (dx, dy) the user has saved for a sheet
        self.layers = []  # (layer name, path to load, georef status or None) in download order
        self.empty = set()  # layer names of tifs that hold no image data
        self.adjusted = set()  # layer names of sheets moved by a shift the user saved
        self.error = None

    def run(self):
        self.target_dir.mkdir(parents=True, exist_ok=True)
        total = sum(e.tif_size or 0 for e in self.editions) or 1
        done = 0
        try:
            ftp = ftpindex.connect()
            try:
                for ed in self.editions:
                    for ext in ftpindex.EXTENSIONS:
                        if ext not in ed.files:
                            continue
                        dest = self.target_dir / ed.files[ext][0]
                        size = ed.files[ext][1]
                        if dest.exists() and (size is None or dest.stat().st_size == size):
                            done += size or 0
                        else:
                            done = self._fetch(ftp, ed, ext, dest, done, total)
                            if done < 0:
                                return False
                    if "tif" in ed.files:
                        tif = self.target_dir / ed.files["tif"][0]
                        shift = self.shifts.get(tif.stem, (0.0, 0.0))
                        path, status = adjust.placed_source(tif, shift)
                        self.layers.append((tif.name, path, status))
                        if any(shift):
                            self.adjusted.add(tif.name)
                        if tiffcheck.is_empty(tif):
                            self.empty.add(tif.name)
                    self.setProgress(100 * min(done, total) / total)
            finally:
                ftp.close()
        except Exception as e:
            self.error = str(e)
            return False
        return True

    def _fetch(self, ftp, ed, ext, dest, done, total):
        """Download to a .part file; return new byte count or -1 if cancelled."""
        part = dest.with_name(dest.name + ".part")
        cancelled = False
        with open(part, "wb") as fh:
            def write(chunk):
                nonlocal done, cancelled
                if self.isCanceled():
                    cancelled = True
                    raise InterruptedError
                fh.write(chunk)
                done += len(chunk)
                self.setProgress(100 * min(done, total) / total)

            try:
                ftp.retrbinary(f"RETR {ftpindex.remote_path(ed, ext)}", write, blocksize=65536)
            except InterruptedError:
                pass
        if cancelled:
            part.unlink(missing_ok=True)
            return -1
        part.replace(dest)
        return done

    def finished(self, result):
        self.on_done(self, result)
