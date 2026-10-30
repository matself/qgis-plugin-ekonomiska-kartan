"""Repair the georeferencing of sheets whose map does not fit the 5x5 km grid cell.

Some sheets are larger than 5000 x 5000 px (e.g. 133_2d5j74_0_b2.tif is 5287 x 5000
with a white margin on the right), but their .tfw / .TAB were generated as if the
whole image were exactly one grid cell. The image is then squeezed (pixel size
0.9457 m instead of 1.0 m). Verified against the base map for 2d5j: the scan is
1.0 m/pixel, the north-west corner is right, and the map neatline ends at the grid
cell edge, i.e. 5000 px from the origin. Everything beyond that is margin.

The downloaded files are never touched; a ``<stem>_fixed.vrt`` is written next to the
tif and loaded instead. Parsing is pure Python so it can be tested without QGIS.
"""
import re
from pathlib import Path

from . import grid

PIXEL = 1.0  # metres, nominal scan resolution of Ekonomiska kartan
TOLERANCE = 1e-3

_TAB_POINT = re.compile(r"\(\s*[-\d.]+\s*,\s*[-\d.]+\s*\)\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")


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


def corrected(tfw, width, height):
    """Corrected placement for a squeezed sheet.

    Returns (ulx, uly, cols, rows): north-west corner and the size in pixels of the part
    of the image that lies inside the grid cell (the rest is margin).
    """
    a, _d, _b, e, c, f = tfw
    ulx = c - a / 2  # world file refers to the pixel centre
    uly = f - e / 2
    cols = min(width, round(grid.SMALL / PIXEL))
    rows = min(height, round(grid.SMALL / PIXEL))
    return ulx, uly, cols, rows


def fixed_vrt_path(tif_path):
    tif_path = Path(tif_path)
    return tif_path.with_name(tif_path.stem + "_fixed.vrt")


def layer_source(tif_path):
    """Path to load for a downloaded tif: the tif itself, or a repaired VRT.

    Returns (path, was_fixed).
    """
    tif_path = Path(tif_path)
    tfw_path = tif_path.with_suffix(".tfw")
    tab_path = tif_path.with_suffix(".TAB")
    if not tab_path.exists():
        tab_path = tif_path.with_suffix(".tab")
    if not (tfw_path.exists() and tab_path.exists()):
        return str(tif_path), False
    try:
        tfw = parse_tfw(tfw_path.read_text())
        width, height = parse_tab_size(tab_path.read_text(errors="replace"))
    except ValueError:
        return str(tif_path), False
    if not is_squeezed(tfw):
        return str(tif_path), False

    from osgeo import gdal  # shipped with QGIS; imported here to keep the module testable

    ulx, uly, cols, rows = corrected(tfw, width, height)
    vrt = fixed_vrt_path(tif_path)
    gdal.Translate(
        str(vrt),
        str(tif_path),
        format="VRT",
        srcWin=[0, 0, cols, rows],
        outputBounds=[ulx, uly, ulx + cols * PIXEL, uly - rows * PIXEL],
        outputSRS=grid.CRS_AUTHID,
    )
    return str(vrt), True
