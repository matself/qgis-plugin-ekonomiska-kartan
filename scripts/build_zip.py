"""Build dist/<module>-<version>.zip, ready for 'Install from ZIP' or plugins.qgis.org."""
import configparser
import zipfile
from pathlib import Path

from compile_translations import compile_ts

MODULE = "ekonomiska_kartan"
ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ROOT / MODULE
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_SUFFIXES = {".pyc", ".ts", ".qm"}  # .qm is compiled from the .ts files below


def read_metadata():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
    return parser["general"]


def zip_name():
    """<module>-<version>[-experimental].zip; experimental follows metadata.txt."""
    meta = read_metadata()
    suffix = "-experimental" if meta.getboolean("experimental", fallback=False) else ""
    return f"{MODULE}-{meta['version']}{suffix}.zip"


def main():
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / zip_name()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN_DIR.rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_dir() or SKIP_DIRS & set(rel.parts) or path.suffix in SKIP_SUFFIXES:
                continue
            zf.write(path, rel.as_posix())
        for ts in sorted((PLUGIN_DIR / "i18n").glob("*.ts")):
            zf.writestr(f"{MODULE}/i18n/{ts.stem}.qm", compile_ts(ts))
        license_file = ROOT / "LICENSE"
        if license_file.exists():
            zf.write(license_file, f"{MODULE}/LICENSE")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
