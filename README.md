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
- Downloads `.tif/.tfw/.TAB` anonymously from `download-opendata.lantmateriet.se` in a
  background task and loads the rasters into a layer group.
- About 1.5 % of the editions are scanned larger than their grid cell and have a wrong
  `.tfw/.TAB`. They are loaded through a cropped `_fixed.vrt`; the list of these editions is
  in `ekonomiska_kartan/data/nonstandard_sheets.csv`. Only a few positions are verified by
  eye - the rest are measured from the image and flagged "(unverified)" when uncertain.

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
