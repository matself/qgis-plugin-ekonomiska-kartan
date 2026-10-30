"""Lantmäteriet open-data FTP: listing, filename matching and file download.

Pure Python (no QGIS imports). File names look like ``133_10a0g79_0_b2.tif``
where ``79`` is the map year, which cannot be computed - hence one LIST per block.
"""
import ftplib
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

HOST = "download-opendata.lantmateriet.se"
ROOT = "/Ekonomiska_kartan"
EXTENSIONS = ("tif", "tfw", "tab")

# 133_<sheet><year>[-n]_0_b2.<ext>; year is missing for a few files
FILE_RE = re.compile(
    r"^133_(?P<ruta>\d+[a-z]\d[a-z])(?P<tail>[^_]*)_0_b2\.(?P<ext>tif|tfw|tab)$",
    re.IGNORECASE,
)
TAIL_RE = re.compile(r"^(?P<year>\d{2})?(?P<suffix>-\d+)?$")


@dataclass
class Edition:
    """One edition of one sheet, with the files that belong to it."""

    ruta: str
    year: int  # two-digit year as in the filename, -1 if unknown
    stem: str  # filename without extension, e.g. 133_10a0g79_0_b2
    directory: str
    files: dict = field(default_factory=dict)  # ext (lower) -> (filename, size or None)

    @property
    def tif_size(self):
        entry = self.files.get("tif")
        return entry[1] if entry else None

    @property
    def sort_key(self):
        # two-digit years: 00-30 are 20xx, the rest 19xx; unknown sorts first
        if self.year < 0:
            return (-1, self.stem)
        return (self.year + (2000 if self.year <= 30 else 1900), self.stem)

    @property
    def label(self):
        return f"19{self.year:02d}" if self.year > 30 else (
            f"20{self.year:02d}" if self.year >= 0 else "?"
        )


def parse_filename(name):
    """Return (ruta, year, stem, ext) or None if the name is not a map file."""
    m = FILE_RE.match(name)
    if m is None:
        return None
    t = TAIL_RE.match(m.group("tail"))
    if t is None:
        return None
    year = int(t.group("year")) if t.group("year") else -1
    stem = name.rsplit(".", 1)[0]
    return m.group("ruta").lower(), year, stem, m.group("ext").lower()


def parse_list_line(line):
    """Parse one unix-style LIST line -> (name, size or None)."""
    parts = line.split(None, 8)
    if len(parts) == 9 and parts[4].isdigit():
        return parts[8], int(parts[4])
    return (line.split()[-1] if line.split() else ""), None


def editions_from_listing(lines, directory):
    """Group LIST lines into {ruta: [Edition, ...]} (oldest first)."""
    by_stem = {}
    for line in lines:
        name, size = parse_list_line(line)
        parsed = parse_filename(name)
        if parsed is None:
            continue
        ruta, year, stem, ext = parsed
        ed = by_stem.setdefault(stem, Edition(ruta, year, stem, directory))
        ed.files[ext] = (name, size)
    result = {}
    for ed in by_stem.values():
        result.setdefault(ed.ruta, []).append(ed)
    for eds in result.values():
        eds.sort(key=lambda e: e.sort_key)
    return result


def latest(editions):
    return max(editions, key=lambda e: e.sort_key)


def connect(timeout=30):
    """Anonymous FTP connection, explicit TLS when the server offers it."""
    ftp = ftplib.FTP_TLS(HOST, timeout=timeout)
    try:
        ftp.login()
        ftp.prot_p()
    except (ftplib.error_perm, ftplib.error_reply, AttributeError):
        ftp.close()  # do not leave the TLS attempt's socket open
        ftp = ftplib.FTP(HOST, timeout=timeout)
        ftp.login()
    return ftp


def list_block(ftp, block):
    """LIST ``/Ekonomiska_kartan/<block>`` and return {ruta: [Edition, ...]}."""
    directory = f"{ROOT}/{block}"
    lines = []
    try:
        ftp.retrlines(f"LIST {directory}", lines.append)
    except (ftplib.error_temp, ftplib.error_perm) as e:
        # The server only has a directory for the 50 km blocks that hold maps (175 of 378),
        # and answers 450/550 "No such file or directory" for the others.
        if str(e).startswith(("450", "550")):
            return {}
        raise
    return editions_from_listing(lines, directory)


def remote_path(edition, ext):
    name = edition.files[ext][0]
    return str(PurePosixPath(edition.directory) / name)
