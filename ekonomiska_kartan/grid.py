"""Sheet grid of Ekonomiska kartan in RT90 2.5 gon V (EPSG:3021).

Pure Python (no QGIS imports) so it can be unit tested without QGIS.

A sheet name such as ``10a3g`` is ``<nr><letter><digit><letter>``:
  * ``nr`` + first letter pick the 50 km block (row, column)
  * ``digit`` + second letter pick the 5 km sheet inside the block (row, column)

Verified against EkoRutor.shp: 12 013 of 12 015 sheets follow the formula. The
irregular edge sheets in ``IRREGULAR`` have shifted geometry; their real extent
is only known from the ``.tfw`` / ``.TAB`` that comes with the download.
"""
import math
import re

CRS_AUTHID = "EPSG:3021"
X0, Y0 = 1_200_000, 6_100_000
BIG, SMALL = 50_000, 5_000

RUTA_RE = re.compile(r"^(\d+)([a-z])(\d)([a-z])$")
IRREGULAR = frozenset({"3c0a", "3e1h"})


def ruta_bounds(name):
    """Return (xmin, ymin, xmax, ymax) in EPSG:3021 for a sheet name."""
    m = RUTA_RE.match(name)
    if m is None:
        raise ValueError(f"Not a sheet name: {name!r}")
    nr, big_col, digit, col = m.groups()
    x = X0 + (ord(big_col) - 97) * BIG + (ord(col) - 97) * SMALL
    y = Y0 + (int(nr) - 1) * BIG + int(digit) * SMALL
    return x, y, x + SMALL, y + SMALL


def ruta_at(x, y):
    """Return the sheet name covering the point (x, y) in EPSG:3021."""
    bx, rx = divmod(x - X0, BIG)
    by, ry = divmod(y - Y0, BIG)
    return f"{int(by) + 1}{chr(97 + int(bx))}{int(ry // SMALL)}{chr(97 + int(rx // SMALL))}"


def storruta(name):
    """Return the 50 km block part of a sheet name, e.g. ``10a`` for ``10a3g``.

    This is also the FTP directory name.
    """
    m = RUTA_RE.match(name)
    if m is None:
        raise ValueError(f"Not a sheet name: {name!r}")
    return m.group(1) + m.group(2)


def rutor_in_bbox(xmin, ymin, xmax, ymax):
    """Names of all sheets intersecting the box (EPSG:3021), sorted."""
    if xmax < xmin or ymax < ymin:
        raise ValueError("Empty bounding box")
    col0 = math.floor((xmin - X0) / SMALL)
    col1 = math.ceil((xmax - X0) / SMALL) - 1
    row0 = math.floor((ymin - Y0) / SMALL)
    row1 = math.ceil((ymax - Y0) / SMALL) - 1
    col1, row1 = max(col0, col1), max(row0, row1)  # degenerate box -> one sheet
    names = []
    for row in range(row0, row1 + 1):
        for col in range(col0, col1 + 1):
            if col < 0 or row < 0:
                continue
            names.append(ruta_at(X0 + col * SMALL, Y0 + row * SMALL))
    return sorted(names)


def storrutor(names):
    """Sorted unique FTP directory names needed for the given sheets."""
    return sorted({storruta(n) for n in names})
