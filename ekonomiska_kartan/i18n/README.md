# Translations

Source strings are English and go through `self.tr()` (dock widget) or
`QCoreApplication.translate("tasks", ...)`. Swedish is in `ekonomiska_kartan_sv.ts`.
`plugin.py` loads `ekonomiska_kartan_<locale>.qm` for the QGIS locale automatically.

After adding or changing a UI string, extract it and translate the new entries
(`pylupdate5` ships with QGIS 3; run it through `python-qgis.bat -m PyQt5.pylupdate_main`):

```bash
cd ekonomiska_kartan
python -m PyQt5.pylupdate_main -noobsolete dockwidget.py tasks.py -ts i18n/ekonomiska_kartan_sv.ts
```

Compile to `.qm` without Qt's lrelease (also done by `scripts/build_zip.py`, so the zip
always has an up to date `.qm`; the `.qm` file itself is not committed):

```bash
python scripts/compile_translations.py
```

`tests/test_translations.py` fails when a string in the code has no Swedish translation.
Use `{count}`-style placeholders instead of plurals.
