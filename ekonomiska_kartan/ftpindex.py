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

# The server keeps a few sheets in the directory of a neighbouring block (found by listing
# every directory): 13h5f and 13h5g are in /13g. block -> other directories to look in.
EXTRA_DIRECTORIES = {"13h": ("13g",)}

# 133_<sheet><year>[-n]_0_b2.<ext>; year is missing for a few files
FILE_RE = re.compile(
    r"^133_(?P<ruta>\d+[a-z]\d[a-z])(?P<tail>[^_]*)_0_b2\.(?P<ext>tif|tfw|tab)$",
    re.IGNORECASE,
)
# After the first sheet name: for a sheet that covers several grid cells (the islands Ven and
# Hanö, georeferenced by hand) the span, e.g. "-b" (3c0a-b = 3c0a and 3c0b) or "-i2h-i"
# (3e1h-i2h-i = 3e1h, 3e1i, 3e2h and 3e2i), then the year and an optional "-n".
TAIL_RE = re.compile(
    r"^(?P<span>(?:-[a-z])?(?:\d[a-z](?:-[a-z])?)*)(?P<year>\d{2})?(?P<suffix>-\d+)?$"
)
ROW_RE = re.compile(r"(\d)([a-z])(?:-([a-z]))?")


@dataclass
class Edition:
    """One edition of one sheet, with the files that belong to it."""

    ruta: str
    year: int  # two-digit year as in the filename, -1 if unknown
    stem: str  # filename without extension, e.g. 133_10a0g79_0_b2
    directory: str
    files: dict = field(default_factory=dict)  # ext (lower) -> (filename, size or None)
    span: str = ""  # e.g. "-b" in 3c0a-b: the sheet covers more than its first grid cell
    covers: tuple = ()  # every grid cell the sheet covers, first one is ``ruta``

    def __post_init__(self):
        if not self.covers:
            self.covers = span_cells(self.ruta, self.span)

    @property
    def sheet(self):
        """Name as written in the file name, e.g. ``3c0a-b`` (just ``ruta`` for most sheets)."""
        return self.ruta + self.span

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


def span_cells(ruta, span):
    """Grid cells a sheet covers: its first cell plus the span written after it.

    ``3c0a`` + ``-b`` -> 3c0a, 3c0b; ``3e1h`` + ``-i2h-i`` -> 3e1h, 3e1i, 3e2h, 3e2i.
    """
    block, digit, col = ruta[:-2], ruta[-2], ruta[-1]
    last = col
    if span.startswith("-"):
        last, span = span[1], span[2:]
    rows = [(digit, col, last)] + [(d, a, b or a) for d, a, b in ROW_RE.findall(span)]
    return tuple(
        f"{block}{d}{chr(c)}" for d, first, end in rows for c in range(ord(first), ord(end) + 1)
    )


def _parse(name):
    m = FILE_RE.match(name)
    if m is None:
        return None
    t = TAIL_RE.match(m.group("tail"))
    return (m, t) if t is not None else None


def parse_filename(name):
    """Return (ruta, year, stem, ext) or None if the name is not a map file."""
    parsed = _parse(name)
    if parsed is None:
        return None
    m, t = parsed
    year = int(t.group("year")) if t.group("year") else -1
    stem = name.rsplit(".", 1)[0]
    return m.group("ruta").lower(), year, stem, m.group("ext").lower()


def span_of(name):
    """The span after the first sheet name (``-b``), empty for an ordinary sheet."""
    parsed = _parse(name)
    return parsed[1].group("span") if parsed else ""


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
        ed = by_stem.setdefault(stem, Edition(ruta, year, stem, directory, span=span_of(name)))
        ed.files[ext] = (name, size)
    result = {}
    for ed in by_stem.values():
        result.setdefault(ed.ruta, []).append(ed)
    for eds in result.values():
        eds.sort(key=lambda e: e.sort_key)
    return result


def directories_for(blocks):
    """FTP directories to list for the given blocks (a few blocks have sheets elsewhere)."""
    return sorted({d for b in blocks for d in (b, *EXTRA_DIRECTORIES.get(b, ()))})


def select_editions(by_ruta, wanted):
    """The editions that cover any of the ``wanted`` cells.

    Returns ({first cell: [Edition, ...]}, set of wanted cells that have a map). A sheet that
    covers several cells is listed once, under its first cell.
    """
    wanted = set(wanted)
    chosen, covered = {}, set()
    for eds in by_ruta.values():
        for ed in eds:
            hit = wanted.intersection(ed.covers)
            if hit:
                chosen.setdefault(ed.ruta, []).append(ed)
                covered |= hit
    for eds in chosen.values():
        eds.sort(key=lambda e: e.sort_key)
    return chosen, covered


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
