"""Background tasks: list FTP blocks and download chosen editions."""
from pathlib import Path

from qgis.core import QgsTask

from . import ftpindex, georef, grid


class ListTask(QgsTask):
    """LIST each needed block directory and collect the editions per sheet."""

    def __init__(self, rutor, on_done):
        super().__init__("Ekonomiska kartan: list available sheets", QgsTask.Flag.CanCancel)
        self.rutor = list(rutor)
        self.on_done = on_done
        self.editions = {}
        self.error = None

    def run(self):
        blocks = grid.storrutor(self.rutor)
        wanted = set(self.rutor)
        try:
            ftp = ftpindex.connect()
            try:
                for i, block in enumerate(blocks):
                    if self.isCanceled():
                        return False
                    for ruta, eds in ftpindex.list_block(ftp, block).items():
                        if ruta in wanted:
                            self.editions[ruta] = eds
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

    def __init__(self, editions, target_dir, on_done):
        super().__init__("Ekonomiska kartan: download", QgsTask.Flag.CanCancel)
        self.editions = list(editions)
        self.target_dir = Path(target_dir)
        self.on_done = on_done
        self.layers = []  # (layer name, path to load, georef repaired) in download order
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
                        path, fixed = georef.layer_source(tif)
                        self.layers.append((tif.name, path, fixed))
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
