import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekonomiska_kartan import adjust  # noqa: E402


class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):  # noqa: N802 (QSettings API)
        self[key] = value


def test_sheet_stem_from_layer_sources():
    stem = "133_3b9i72_0_b2"
    assert adjust.sheet_stem(rf"C:\data\{stem}.tif") == stem
    assert adjust.sheet_stem(f"/data/{stem}_fixed.vrt") == stem
    assert adjust.sheet_stem(f"/data/{stem}_adjusted.vrt|layername=x") == stem
    assert adjust.sheet_stem("/data/133_3e1h-i2h-i71_0_b2.tif") == "133_3e1h-i2h-i71_0_b2"
    assert adjust.sheet_stem("/data/ortofoto.tif") is None
    assert adjust.sheet_stem("") is None


def test_parse_shifts_drops_bad_entries():
    text = '{"a": [1, 2], "b": [0, 0], "c": [1e9, 0], "d": "x", "e": [1], "f": [-2000, 0]}'
    assert adjust.parse_shifts(text) == {"a": (1.0, 2.0), "f": (-2000.0, 0.0)}
    assert adjust.parse_shifts("") == {}
    assert adjust.parse_shifts("not json") == {}
    assert adjust.parse_shifts("[1, 2]") == {}


def test_store_remembers_changes_and_forgets_zero():
    settings = FakeSettings()
    adjust.store(settings, "133_3b9i72_0_b2", 2000, 0)
    adjust.store(settings, "133_3b8j72_0_b2", -3.5, 12)
    assert adjust.load(settings) == {
        "133_3b9i72_0_b2": (2000.0, 0.0),
        "133_3b8j72_0_b2": (-3.5, 12.0),
    }
    adjust.store(settings, "133_3b9i72_0_b2", 0, 0)  # reset
    assert adjust.load(settings) == {"133_3b8j72_0_b2": (-3.5, 12.0)}
    adjust.store(settings, "133_3b8j72_0_b2", 5e6, 0)  # absurd values are not stored
    assert adjust.load(settings) == {}


def test_shifted_bounds_north_up():
    gt = (1290000.0, 1.0, 0.0, 6250000.0, 0.0, -1.0)
    assert adjust.shifted_bounds(gt, 5379, 5000, 2000, -15) == [
        1292000.0,
        6249985.0,
        1297379.0,
        6244985.0,
    ]


def test_adjusted_vrt_next_to_the_tif():
    vrt = adjust.adjusted_vrt_path("/d/133_3b9i72_0_b2.tif")
    assert vrt == Path("/d/133_3b9i72_0_b2_adjusted.vrt")


def test_placed_source_without_shift_is_the_normal_placement(tmp_path):
    tif = tmp_path / "133_9z9z99_0_b2.tif"
    tif.write_bytes(b"")
    assert adjust.placed_source(tif) == (str(tif), None)  # no .tfw/.TAB: loaded as it is


def test_placed_source_moves_the_sheet(tmp_path):
    np = pytest.importorskip("numpy")
    gdal = pytest.importorskip("osgeo.gdal")
    path = tmp_path / "133_9z9z99_0_b2.tif"
    ds = gdal.GetDriverByName("GTiff").Create(str(path), 40, 30, 3, gdal.GDT_Byte)
    ds.SetGeoTransform((1000.0, 1.0, 0.0, 5000.0, 0.0, -1.0))
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(np.full((30, 40), 7, dtype=np.uint8))
    ds = None
    vrt, status = adjust.placed_source(path, (2000.0, -15.0))
    assert vrt.endswith("_adjusted.vrt") and status is None
    out = gdal.Open(vrt)
    assert (out.RasterXSize, out.RasterYSize) == (40, 30)
    assert out.GetGeoTransform() == pytest.approx((3000.0, 1.0, 0.0, 4985.0, 0.0, -1.0))
    assert out.GetRasterBand(1).ReadAsArray()[0, 0] == 7  # same pixels, other place
