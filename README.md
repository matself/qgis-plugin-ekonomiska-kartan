<img src="ekonomiska_kartan/icon.svg" alt="Plugin icon" width="72" height="72" align="right">

# Geodata: Ekonomiska kartan (Lantmäteriet)

> **Experimental pre-release (0.1.0).** Expect rough edges; please report problems in the
> [issue tracker](https://github.com/matself/qgis-plugin-ekonomiska-kartan/issues).

*Svensk steg-för-steg-handledning: [HANDLEDNING.md](HANDLEDNING.md).*

QGIS plugin to find, download and load the scanned *Ekonomiska kartan* sheets that
Lantmäteriet publishes as open data.

- Pick an area: draw a search box on the map or use the current map extent.
- The 5x5 km sheet grid (EPSG:3021, RT90 2.5 gon V) can be added to the map as a layer; it
  follows the map and switches to 50 km blocks when zoomed out. Hide or remove it in the layer
  list. **The grid is synthetic: computed from the sheet naming scheme, not Lantmäteriet's real
  sheet extents** (see below). It is a search aid, not a map of where the sheets really lie.
- The sheets found are outlined on the map: grey when listed, green when ticked for download,
  with a thick orange outline for the row you have selected in the list.
- "Pick sheets on map" ticks and unticks the listed sheets from the map: click a sheet to toggle
  it, drag a rectangle to select several (Shift adds, Ctrl removes).
- Sheets with several editions (years) get an edition selector; the latest is the default.
- Sheets that cover several grid cells (the islands Ven and Hanö, `3c0a-b` and `3e1h-i2h-i`) are
  listed once and loaded with their own georeferencing.
- Downloads `.tif/.tfw/.TAB` anonymously from `download-opendata.lantmateriet.se` in a
  background task and loads the rasters into a layer group.
- About 1.5 % of the editions (187) are scanned larger than their grid cell: Lantmäteriet
  enlarged those sheets towards a side without a neighbour sheet, but wrote a `.tfw/.TAB` that
  squeezes the whole scan into one cell. They are loaded through a `_fixed.vrt` that places the
  whole scan at 1 m/pixel, so the extra map outside the cell is kept. The side is taken from the
  checklist `ekonomiska_kartan/data/nonstandard_sheets.csv`: verified by eye (6 sheets), inferred
  from the missing neighbour sheet (130 of 187, `scripts/infer_offsets.py`), otherwise measured from
  the image and flagged "(unverified)" when uncertain. A few pixels of difference are within
  the scanning and rectification accuracy and are not corrected. One verified sheet, `3b9i`
  (Kullen, 1972), also lies 2000 m east of its grid cell: the offset is negative there
  (`-2000,0`), checked against the two lighthouses on the sheet and the seam to `3b8j`.

## Not covered

The plugin finds sheets from a synthetic 5x5 km grid (EPSG:3021) that it computes itself, and
loads the `.tif/.tfw/.TAB` of each sheet. The grid is computed on purpose, so that the plugin
does not have to ship Lantmäteriet's large index file with the real sheet extents; it matches the
real index for all but 2 of 12 015 sheets, but it is still not the real extent. That is why only
data with a georeferenced sheet in that grid is covered. Left out on purpose:

- **`Norrlands_inland`** on the same server: a separate series of about 1 050 scans (roughly
  80 MB each) with their own names (`141_15c2-3g-h77_0.tif`), no `.tfw/.TAB` and no coordinates.
  Their position is only given by an index shapefile (`Norrlands_Inland.shp`), so loading them
  would mean reading that index and placing every scan ourselves, a different job from loading
  sheets that already carry their georeferencing.
- **Sheet `4e6f`** (1952 and 1979): on the server only as ungeoreferenced `.tiff` scans
  (6450 x 6221 px, no `.tfw/.TAB`), so it shows up as "without map" although all its neighbours
  have one.
- **`Bladindelningskartor`**: PDF overview maps of the sheet division, not map sheets.

## Quality of the source data

The maps were scanned and registered by Lantmäteriet long ago, and neither the files nor the
server directories are free of errors. The plugin handles the systematic cases it has come
across (oversized sheets, sheets that cover several cells, sheets filed in a neighbouring
directory) and flags a sheet whose image is empty, but it does not try to find and correct every
defect. Expect to meet others, for example:

- sheets or editions that are missing, or placed wrongly;
- file names that break the naming pattern;
- images that are blank, black or damaged (sheet `3d9e`, 1976, is a tif with an empty tile
  table: it shows as plain black although the file is 43 MB, and is loaded as "(empty)");
- georeferencing that is off by a few pixels or more;
- sheets that only exist as scans without coordinates.

Check what you load against a base map. If you find a defect that affects many sheets, please
open an issue.

## Install

Download `ekonomiska_kartan-0.1.0-experimental.zip` from the
[Releases](https://github.com/matself/qgis-plugin-ekonomiska-kartan/releases) page and use
*Plugins > Manage and Install Plugins > Install from ZIP*. Tick *Show also experimental plugins*
if you install through the plugin repository instead.

Compatible with QGIS 3.34 up to 4.99 (Qt5 and Qt6).

## Development

Link the plugin folder into your QGIS profile so changes are picked up (use the Plugin Reloader plugin):

```powershell
# Windows (run once, adjust profile name if needed)
New-Item -ItemType Junction `
  -Path "$env:APPDATA\QGIS\QGIS4\profiles\default\python\plugins\ekonomiska_kartan" `
  -Target "$PWD\ekonomiska_kartan"
```

Build an installable zip:

```bash
python scripts/build_zip.py   # -> dist/ekonomiska_kartan-0.1.0-experimental.zip
```

## Qt5 / Qt6 compatibility rules

- Import Qt only via `qgis.PyQt`, never `PyQt5` / `PyQt6`.
- Use fully scoped enums (`Qt.DockWidgetArea.RightDockWidgetArea`).
- Use `exec()`, not `exec_()`.
- Put anything that differs between QGIS 3 and 4 in `ekonomiska_kartan/compat.py`.
- plugins.qgis.org runs an automatic Qt6 check on upload (see the *Qt6 Check* tab).

## License

GPL-2.0-or-later - see [LICENSE](LICENSE).
