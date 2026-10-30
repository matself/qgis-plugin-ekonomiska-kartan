<img src="ekonomiska_kartan/icon.svg" alt="Plugin icon" width="72" height="72" align="right">

# Geodata: Ekonomiska kartan (Lantmäteriet)

> **Experimental pre-release (0.1.0).** Expect rough edges; please report problems in the
> [issue tracker](https://github.com/matself/qgis-plugin-ekonomiska-kartan/issues).

QGIS plugin to find, download and load the scanned *Ekonomiska kartan* sheets that
Lantmäteriet publishes as open data.

- Pick an area: draw a search box on the map or use the current map extent.
- The 5x5 km sheet grid (EPSG:3021, RT90 2.5 gon V) is shown on the map and switches to
  50 km blocks when zoomed out.
- Sheets with several editions (years) get an edition selector; the latest is the default.
- Sheets that cover several grid cells (the islands Ven and Hanö, `3c0a-b` and `3e1h-i2h-i`) are
  listed once and loaded with their own georeferencing.
- Downloads `.tif/.tfw/.TAB` anonymously from `download-opendata.lantmateriet.se` in a
  background task and loads the rasters into a layer group.
- About 1.5 % of the editions (187) are scanned larger than their grid cell: Lantmäteriet
  enlarged those sheets towards a side without a neighbour sheet, but wrote a `.tfw/.TAB` that
  squeezes the whole scan into one cell. They are loaded through a `_fixed.vrt` that places the
  whole scan at 1 m/pixel, so the extra map outside the cell is kept. The side is taken from the
  checklist `ekonomiska_kartan/data/nonstandard_sheets.csv`: verified by eye (5 sheets), inferred
  from the missing neighbour sheet (130 of 187, `scripts/infer_offsets.py`), otherwise measured from
  the image and flagged "(unverified)" when uncertain. A few pixels of difference are within
  the scanning and rectification accuracy and are not corrected.

## Not covered

The plugin finds sheets from a synthetic 5x5 km grid (EPSG:3021) that it computes itself, and
loads the `.tif/.tfw/.TAB` of each sheet. That is why only data with a georeferenced sheet in
that grid is covered. Left out on purpose:

- **`Norrlands_inland`** on the same server: a separate series of about 1 050 scans (roughly
  80 MB each) with their own names (`141_15c2-3g-h77_0.tif`), no `.tfw/.TAB` and no coordinates.
  Their position is only given by an index shapefile (`Norrlands_Inland.shp`), so loading them
  would mean reading that index and placing every scan ourselves, a different job from loading
  sheets that already carry their georeferencing.
- **Sheet `4e6f`** (1952 and 1979): on the server only as ungeoreferenced `.tiff` scans
  (6450 x 6221 px, no `.tfw/.TAB`), so it shows up as "without map" although all its neighbours
  have one.
- **`Bladindelningskartor`**: PDF overview maps of the sheet division, not map sheets.

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
