# Experiment: georeferencing Norrlands_inland

Not part of the plugin and not on `main`. Kept here because it works on the sheets tried, and
may be useful to whoever wants to georeference this series.

## The data

`Norrlands_inland` on `download-opendata.lantmateriet.se/Ekonomiska_kartan/` is a separate
series, not covered by the plugin:

- 1 046 directories, each with one scan `141_<sheet>_0.tif` (about 81 MB, 3 band RGB), for
  example `J141-17F0-1a-b73/141_17f0-1a-b73_0.tif`
- no `.tfw`, no `.TAB`, no coordinates in the tif
- an index `Norrlands_Inland.shp` (SWEREF 99 TM, EPSG:3006) with one polygon per sheet and the
  fields `Kartserie`, `Bladnummer`, `Bladnamn` and `År`
- the sheet name follows the plugin's grid scheme: `17F0-1a-b` is block 17F, rows 0-1, columns
  a-b, so most sheets are 2 x 2 cells = 10 x 10 km (966 of 1 046; the rest are cut by the
  Norwegian border or the coast)
- the polygons are RT90 squares drawn in SWEREF: a square of 9 994 m, rotated about 0.7 degrees

## How a sheet is placed

1. The scan is 5210 x 5210 px; the map frame is about 4 997 px (2 m/px, read from the printed
   2 km grid). The rest is margin, 60-160 px wide and different on every side.
2. Each scan has a thin L-shaped mark at the four corners of the frame. `find_marks` looks for an
   L (ink on the legs, paper around it) in a window at each corner.
3. The four marks are matched to the four polygon corners and the scan is warped with a first
   order polynomial, which absorbs scanner skew (about 0.3 degrees) and a slightly off scale.

## What was tried

Two interior sheets with four neighbours each, Buan (`J141-17F0-1a-b73`) and Stensån
(`J141-17F0-1c-d73`), both 1973:

| | TL | TR | BR | BL |
|---|---|---|---|---|
| Buan, mark score | 0.88 | 0.95 | 1.00 | 0.97 |
| Stensån, mark score | 0.74 | 0.54 | 0.89 | 0.92 |

Placed with the polygon corners and put side by side, the map continues over the shared edge
(roads, estate boundaries, contours). No gap; the best vertical shift between the sheets is
about 5 px (10 m), with a weak preference over no shift. Not compared with an independent base
map, and only one pair of interior sheets.

## What was not solved

- Edge sheets: a sheet on the Norwegian border is mostly white paper, so margin and map cannot
  be told apart without the marks, and the marks may be harder to find there.
- Low scores (Stensån TR 0.54) would need a check or a warning before loading.
- The 80 sheets that are not regular 10 x 10 km squares have other polygons.
- Nothing downloads the scans or lists the series.

## Running it

With the Python that ships with QGIS:

```
python place_sheets.py marks SCAN.tif
python place_sheets.py place INDEX.shp J141-17F0-1a-b73 SCAN.tif OUT.tif
python place_sheets.py seam INDEX.shp SHEET_A SCAN_A.tif SHEET_B SCAN_B.tif seam.png
```

`seam` writes a mosaic of 4 x 4 km around the shared edge of two neighbouring sheets (B is the
east neighbour of A).
