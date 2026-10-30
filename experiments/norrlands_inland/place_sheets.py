"""Prototype: georeference scans from Lantmäteriet's Norrlands_inland series.

The scans (``Norrlands_inland/J141-.../141_..._0.tif``) have no coordinates. The index
``Norrlands_Inland.shp`` gives the four corners of every 10 x 10 km sheet in SWEREF 99 TM, and
each scan carries thin L-shaped corner marks at the corners of the map frame. Matching the four
marks to the four polygon corners places the scan (first order polynomial, so scanner skew and
a slightly off scale are absorbed).

Run it with the Python that ships with QGIS (needs gdal, ogr and numpy)::

    python place_sheets.py marks  SCAN.tif
    python place_sheets.py place  INDEX.shp SHEET SCAN.tif OUT.tif
    python place_sheets.py seam   INDEX.shp SHEET_A SCAN_A.tif SHEET_B SCAN_B.tif OUT.png

Findings and limits are in README.md. Not part of the plugin.
"""
import argparse
import sys

import numpy as np
from osgeo import gdal, ogr

gdal.UseExceptions()
ogr.UseExceptions()

LEG = 20  # length in px of each leg of a corner mark
SEARCH = (30, 200)  # the marks lie 60-160 px from the image edge on the sheets checked
DARK = 120  # a pixel is "ink" when its darkest band is below this
PIXEL = 2.0  # m/px, read from the printed 2 km grid; the frame is about 4 997 px


def load_polygons(shp):
    """{Bladnummer: [NW, NE, SE, SW]} in SWEREF 99 TM, in the order the shapefile stores them."""
    source = ogr.Open(shp)
    out = {}
    for feature in source.GetLayer():
        ring = feature.GetGeometryRef().GetGeometryRef(0)
        out[feature.GetField("Bladnummer")] = [ring.GetPoint(i)[:2] for i in range(4)]
    return out


def ink_mask(tif):
    ds = gdal.Open(tif)
    bands = [ds.GetRasterBand(i + 1).ReadAsArray() for i in range(min(ds.RasterCount, 3))]
    return np.minimum.reduce(bands) < DARK


def mark_score(mask, x, y, sx, sy):
    """How well an L with its vertex at (x, y) and legs towards (sx, sy) fits: ink on the legs,
    paper around them and behind the vertex (the frame side)."""
    on = ring = behind = 0
    for k in range(LEG + 1):
        for w in (0, 1):
            on += int(mask[y + sy * k, x + w]) + int(mask[y + w, x + sx * k])
    for k in range(3, LEG + 1):
        for w in (-3, -2, 3, 4):
            ring += int(mask[y + sy * k, x + w]) + int(mask[y + w, x + sx * k])
    for k in range(3, 10):
        for w in (0, 1):
            behind += int(mask[y + w, x - sx * k]) + int(mask[y - sy * k, x + w])
    return on / (2 * (LEG + 1) * 2) - 0.5 * ring / (2 * (LEG - 2) * 4) - 0.5 * behind / 28


def find_marks(mask):
    """Vertices of the four corner marks: {"TL"|"TR"|"BR"|"BL": ((x, y), score)}."""
    h, w = mask.shape
    lo, hi = SEARCH
    windows = {  # legs point away from the frame
        "TL": (-1, -1, (lo, lo, hi, hi)),
        "TR": (1, -1, (w - hi, lo, w - lo, hi)),
        "BR": (1, 1, (w - hi, h - hi, w - lo, h - lo)),
        "BL": (-1, 1, (lo, h - hi, hi, h - lo)),
    }
    found = {}
    for name, (sx, sy, (x0, y0, x1, y1)) in windows.items():
        best = (-9.0, None)
        for y in range(y0, y1):
            for x in range(x0, x1):
                best = max(best, (mark_score(mask, x, y, sx, sy), (x, y)))
        found[name] = (best[1], best[0])
    return found


def place(shp, sheet, tif, out, bounds=None):
    """Warp the scan to SWEREF 99 TM from the corner marks, cut to the sheet polygon."""
    marks = find_marks(ink_mask(tif))
    pixels = [marks[k][0] for k in ("TL", "TR", "BR", "BL")]
    gcps = [
        gdal.GCP(x, y, 0, px, py) for (px, py), (x, y) in zip(pixels, load_polygons(shp)[sheet])
    ]
    tmp = gdal.Translate("", tif, format="VRT", GCPs=gcps, outputSRS="EPSG:3006")
    gdal.Warp(
        out, tmp, dstSRS="EPSG:3006", polynomialOrder=1, xRes=PIXEL, yRes=PIXEL, dstAlpha=True,
        outputBounds=bounds, cutlineDSName=shp, cutlineWhere=f"Bladnummer = '{sheet}'",
        resampleAlg="bilinear",
    )
    return marks


def seam(shp, sheet_a, tif_a, sheet_b, tif_b, out_png):
    """Place two neighbouring sheets and write a mosaic of 4 x 4 km over their shared edge."""
    polygons = load_polygons(shp)
    (x, y) = polygons[sheet_a][1]  # NE corner of A = NW corner of B (east neighbour)
    bounds = (x - 2000, y - 6000, x + 2000, y - 2000)
    layers = []
    for sheet, tif in ((sheet_a, tif_a), (sheet_b, tif_b)):
        warped = f"/vsimem/{sheet}.tif"
        place(shp, sheet, tif, warped, bounds)
        layers.append(gdal.Open(warped).ReadAsArray())
    a, b = layers
    mosaic = np.where(a[3] > 0, a[:3], 255).astype(np.uint8)
    mosaic = np.where(b[3] > 0, b[:3], mosaic)
    ds = gdal.GetDriverByName("MEM").Create("", mosaic.shape[2], mosaic.shape[1], 3, gdal.GDT_Byte)
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(mosaic[i])
    gdal.GetDriverByName("PNG").CreateCopy(out_png, ds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("marks").add_argument("tif")
    p = sub.add_parser("place")
    for name in ("shp", "sheet", "tif", "out"):
        p.add_argument(name)
    s = sub.add_parser("seam")
    for name in ("shp", "sheet_a", "tif_a", "sheet_b", "tif_b", "out"):
        s.add_argument(name)
    args = parser.parse_args(argv)
    if args.command == "marks":
        for name, (pos, score) in find_marks(ink_mask(args.tif)).items():
            print(f"{name}: vertex {pos} score {score:.2f}")
    elif args.command == "place":
        marks = place(args.shp, args.sheet, args.tif, args.out)
        print({k: (v[0], round(v[1], 2)) for k, v in marks.items()})
    else:
        seam(args.shp, args.sheet_a, args.tif_a, args.sheet_b, args.tif_b, args.out)
        print("wrote", args.out)


if __name__ == "__main__":
    sys.exit(main())
