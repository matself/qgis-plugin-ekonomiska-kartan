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

N_BLOCK_COLS, N_BLOCK_ROWS = 14, 27  # blocks a-n, 1-27
N_COLS, N_ROWS = N_BLOCK_COLS * 10, N_BLOCK_ROWS * 10


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


def _cell_range(lo, hi, origin, size, count):
    first = math.floor((lo - origin) / size)
    last = max(first, math.ceil((hi - origin) / size) - 1)  # degenerate box -> one cell
    return max(first, 0), min(last, count - 1)


def count_in_bbox(xmin, ymin, xmax, ymax):
    """Number of sheets intersecting the box (cheap, no names built)."""
    c0, c1 = _cell_range(xmin, xmax, X0, SMALL, N_COLS)
    r0, r1 = _cell_range(ymin, ymax, Y0, SMALL, N_ROWS)
    return max(0, c1 - c0 + 1) * max(0, r1 - r0 + 1)


def rutor_in_bbox(xmin, ymin, xmax, ymax):
    """Names of all sheets intersecting the box (EPSG:3021), sorted.

    Cells outside the grid (a-n, 1-27) are ignored.
    """
    if xmax < xmin or ymax < ymin:
        raise ValueError("Empty bounding box")
    c0, c1 = _cell_range(xmin, xmax, X0, SMALL, N_COLS)
    r0, r1 = _cell_range(ymin, ymax, Y0, SMALL, N_ROWS)
    return sorted(
        ruta_at(X0 + col * SMALL, Y0 + row * SMALL)
        for row in range(r0, r1 + 1)
        for col in range(c0, c1 + 1)
    )


def storruta_bounds(name):
    """(xmin, ymin, xmax, ymax) of a 50 km block such as ``10a``."""
    m = re.match(r"^(\d+)([a-z])$", name)
    if m is None:
        raise ValueError(f"Not a block name: {name!r}")
    x = X0 + (ord(m.group(2)) - 97) * BIG
    y = Y0 + (int(m.group(1)) - 1) * BIG
    return x, y, x + BIG, y + BIG


def storrutor_in_bbox(xmin, ymin, xmax, ymax):
    """Names of all 50 km blocks intersecting the box, sorted."""
    c0, c1 = _cell_range(xmin, xmax, X0, BIG, N_BLOCK_COLS)
    r0, r1 = _cell_range(ymin, ymax, Y0, BIG, N_BLOCK_ROWS)
    return sorted(
        f"{row + 1}{chr(97 + col)}" for row in range(r0, r1 + 1) for col in range(c0, c1 + 1)
    )


def storrutor(names):
    """Sorted unique FTP directory names needed for the given sheets."""
    return sorted({storruta(n) for n in names})
