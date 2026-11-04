"""A shift the user applies to a sheet that lies in the wrong place.

The user sees against a base map how far a sheet is off and enters the distance east and north.
The downloaded files are never touched: a ``<stem>_adjusted.vrt`` places the same pixels at the
shifted position. The shift is remembered per sheet (in the QGIS settings of this computer) and
applied again whenever the plugin loads that sheet. Everything except writing the VRT is pure
Python so it can be tested without QGIS.
"""
import json
from pathlib import Path

from . import ftpindex, georef, grid

SETTINGS_KEY = "ekonomiska_kartan/adjustments"
LIMIT = 100_000  # metres; a larger shift is not a correction of a sheet
SUFFIXES = ("_fixed", "_adjusted")  # VRT files this plugin writes next to a tif


def sheet_stem(source):
    """The sheet name (``133_3b9i72_0_b2``) behind a layer source, None if it is not a sheet."""
    stem = Path(str(source).split("|")[0]).stem
    for suffix in SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem if ftpindex.parse_filename(stem + ".tif") else None


def parse_shifts(text):
    """{stem: (dx, dy)} from the stored JSON text; malformed or empty entries are dropped."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    shifts = {}
    for stem, value in data.items() if isinstance(data, dict) else ():
        try:
            dx, dy = (float(v) for v in value)
        except (TypeError, ValueError):
            continue
        if abs(dx) <= LIMIT and abs(dy) <= LIMIT and (dx or dy):
            shifts[str(stem)] = (dx, dy)
    return shifts


def dump_shifts(shifts):
    return json.dumps({stem: list(v) for stem, v in sorted(shifts.items())})


def load(settings):
    """All saved shifts. ``settings`` is a QSettings (anything with ``value``/``setValue``)."""
    return parse_shifts(settings.value(SETTINGS_KEY, ""))


def store(settings, stem, dx, dy):
    """Remember the shift of one sheet; a zero shift forgets it."""
    shifts = load(settings)
    shifts.pop(stem, None)
    shifts.update(parse_shifts(dump_shifts({stem: (dx, dy)})))
    settings.setValue(SETTINGS_KEY, dump_shifts(shifts))


def adjusted_vrt_path(tif_path):
    tif_path = Path(tif_path)
    return tif_path.with_name(tif_path.stem + "_adjusted.vrt")


def shifted_bounds(gt, width, height, dx, dy):
    """[ulx, uly, lrx, lry] of a north-up raster with geotransform ``gt``, moved by (dx, dy)."""
    west, north = gt[0] + dx, gt[3] + dy
    return [west, north, west + width * gt[1], north + height * gt[5]]


def placed_source(tif_path, shift=(0.0, 0.0)):
    """What to load for a downloaded tif: its normal placement, moved by ``shift`` (metres).

    Returns (path, status) like ``georef.layer_source``; with a shift the path is an
    ``_adjusted.vrt`` and the status is that of the normal placement.
    """
    base, status = georef.layer_source(tif_path)
    dx, dy = shift
    if not (dx or dy):
        return base, status

    from osgeo import gdal  # shipped with QGIS; imported here to keep the module testable

    src = gdal.Open(base)
    gt, width, height = src.GetGeoTransform(), src.RasterXSize, src.RasterYSize
    src = None
    vrt = adjusted_vrt_path(tif_path)
    gdal.Translate(
        str(vrt),
        str(tif_path),
        format="VRT",
        outputBounds=shifted_bounds(gt, width, height, dx, dy),
        outputSRS=grid.CRS_AUTHID,
    )
    return str(vrt), status
