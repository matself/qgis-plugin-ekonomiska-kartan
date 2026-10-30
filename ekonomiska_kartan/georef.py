"""Repair the georeferencing of sheets whose map does not fit the 5x5 km grid cell.

187 of the 12 012 sheet editions are larger than 5000 x 5000 px (never smaller): the
scan is the grid cell plus extra margin on one or more sides. Their .tfw / .TAB were
generated as if the whole image were exactly one cell, so the image is squeezed
(pixel size e.g. 0.9457 m instead of 1.0 m). Checked against the base map: the scan is
1.0 m/pixel and the map neatline is exactly one cell (5000 px) wide, but the margin can
be on any side (west coast sheets have it on the left), which the metadata does not say.

Where the cell lies inside the image is therefore found in this order:
  1. ``data/nonstandard_sheets.csv``, column ``verified_offset`` (checked by eye),
  2. measured from the image: the 5000 px window with paper-white margin just outside it.
Measured results with a small cost gap are flagged as unverified.

The downloaded files are never touched; a ``<stem>_fixed.vrt`` cropped to the grid cell is
written next to the tif and loaded instead. Everything except the measuring is pure
Python so it can be tested without QGIS.
"""
import csv
import re
from functools import lru_cache
from itertools import accumulate
from pathlib import Path

from . import grid

PIXEL = 1.0  # metres, nominal scan resolution of Ekonomiska kartan
TOLERANCE = 1e-3
CELL_PX = round(grid.SMALL / PIXEL)
WHITE = 225  # a pixel counts as paper when all bands are above this
CONFIDENT_GAP = 5.0  # cost gap to the next-best offset below which a result is unverified
DATA_FILE = Path(__file__).parent / "data" / "nonstandard_sheets.csv"

_TAB_POINT = re.compile(
    r"^\s*\(\s*[-\d.]+\s*,\s*[-\d.]+\s*\)\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*Label", re.M
)

VERIFIED, MEASURED, UNVERIFIED = "verified", "measured", "unverified"


def parse_tfw(text):
    """Return (a, d, b, e, c, f) from a world file."""
    values = [float(line) for line in text.split() if line.strip()]
    if len(values) != 6:
        raise ValueError("World file must contain six numbers")
    return tuple(values)


def parse_tab_size(text):
    """Image size (width, height) in pixels from the control points of a MapInfo .TAB."""
    points = [(float(x), float(y)) for x, y in _TAB_POINT.findall(text)]
    if not points:
        raise ValueError("No control points in TAB file")
    return round(max(p[0] for p in points)), round(max(p[1] for p in points))


def is_squeezed(tfw):
    a, _d, _b, e, _c, _f = tfw
    return abs(abs(a) - PIXEL) > TOLERANCE or abs(abs(e) - PIXEL) > TOLERANCE


def best_offset(profile, cell=CELL_PX, exclude=25):
    """Where a ``cell`` px window fits best in a paper-fraction profile along one axis.

    ``profile[i]`` is the fraction of paper-white pixels in column (or row) ``i``. The
    columns outside the window should be paper. Returns (offset, gap): ``gap`` is how much
    worse the next-best offset (not a neighbour within ``exclude`` px) is; small = unsure.
    """
    n = len(profile)
    extra = n - cell
    if extra <= 0:
        return 0, float("inf")
    prefix = [0.0, *accumulate(1.0 - v for v in profile)]
    costs = [prefix[k] + (prefix[n] - prefix[k + cell]) for k in range(extra + 1)]
    best = min(range(extra + 1), key=costs.__getitem__)
    others = [c for i, c in enumerate(costs) if abs(i - best) > exclude] or [
        c for i, c in enumerate(costs) if i != best
    ]
    return best, (min(others) - costs[best]) if others else float("inf")


def paper_profiles(tif_path):
    """(column profile, row profile) of the paper-white fraction. Needs gdal + numpy."""
    import numpy as np
    from osgeo import gdal

    ds = gdal.Open(str(tif_path))
    lowest = None
    for i in range(1, ds.RasterCount + 1):
        band = ds.GetRasterBand(i).ReadAsArray()
        lowest = band if lowest is None else np.minimum(lowest, band)
    white = lowest > WHITE
    return white.mean(axis=0).tolist(), white.mean(axis=1).tolist()


@lru_cache(maxsize=1)
def _known():
    out = {}
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                out[row["stem"].lower()] = row["verified_offset"].strip()
    return out


def is_listed(stem):
    """True if the edition is known to be larger than its grid cell."""
    return stem.lower() in _known()


def known_offset(stem):
    """Verified (kx, ky) margin in px before the cell (left, top), or None."""
    value = _known().get(stem.lower(), "")
    if not value:
        return None
    kx, ky = value.split(",")
    return int(kx), int(ky)


def fixed_vrt_path(tif_path):
    tif_path = Path(tif_path)
    return tif_path.with_name(tif_path.stem + "_fixed.vrt")


def locate_cell(stem, tif_path, width, height, cell=CELL_PX):
    """(kx, ky, status): px of margin left of / above the cell inside the image."""
    known = known_offset(stem)
    if known is not None:
        return known[0], known[1], VERIFIED
    cols, rows = paper_profiles(tif_path)
    kx, gap_x = best_offset(cols, cell) if width > cell else (0, float("inf"))
    ky, gap_y = best_offset(rows, cell) if height > cell else (0, float("inf"))
    status = MEASURED if min(gap_x, gap_y) >= CONFIDENT_GAP else UNVERIFIED
    return kx, ky, status


def layer_source(tif_path, cell=CELL_PX):
    """What to load for a downloaded tif.

    Returns (path, status): status is None for a normal sheet, otherwise VERIFIED,
    MEASURED or UNVERIFIED for a repaired ``_fixed.vrt``.
    """
    tif_path = Path(tif_path)
    tfw_path = tif_path.with_suffix(".tfw")
    tab_path = tif_path.with_suffix(".TAB")
    if not tab_path.exists():
        tab_path = tif_path.with_suffix(".tab")
    if not (tfw_path.exists() and tab_path.exists()):
        return str(tif_path), None
    try:
        tfw = parse_tfw(tfw_path.read_text())
        width, height = parse_tab_size(tab_path.read_text(errors="replace"))
    except ValueError:
        return str(tif_path), None
    if not is_squeezed(tfw):
        return str(tif_path), None

    a, _d, _b, e, c, f = tfw
    cell_x, cell_top = c - a / 2, f - e / 2  # north-west corner of the cell (tfw = pixel centre)
    kx, ky, status = locate_cell(tif_path.stem, tif_path, width, height, cell)
    cols, rows = min(cell, width - kx), min(cell, height - ky)

    from osgeo import gdal  # shipped with QGIS; imported here to keep the module testable

    vrt = fixed_vrt_path(tif_path)
    gdal.Translate(
        str(vrt),
        str(tif_path),
        format="VRT",
        srcWin=[kx, ky, cols, rows],
        outputBounds=[cell_x, cell_top, cell_x + cols * PIXEL, cell_top - rows * PIXEL],
        outputSRS=grid.CRS_AUTHID,
    )
    return str(vrt), status
