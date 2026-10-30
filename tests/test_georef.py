import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekonomiska_kartan import georef  # noqa: E402

# 133_2d5j74_0_b2: a 5287 x 5000 px scan squeezed into one 5 km cell
TFW_BAD = "0.9457159069\n0.0\n0.0\n-1.0\n1395000.4728579535\n6179999.5\n"
TFW_OK = "1.0\n0.0\n0.0\n-1.0\n1560000.5\n6329999.5\n"
TAB_BAD = """!table
Definition Table
  File "133_2d5j74_0_b2.tif"
  Type "RASTER"
  (1395000,6180000) (0,0) Label "Pt 1",
  (1400000,6180000) (5287,0) Label "Pt 2",
  (1395000,6175000) (0,5000) Label "Pt 3"
  CoordSys Earth Projection 8, 112, "m", 15.8082777778, 0, 1, 1500000, 0 Bounds (1130000, 6107000) (1833000, 7687000)
"""  # noqa: E501


def test_parse():
    assert georef.parse_tfw(TFW_BAD)[0] == pytest.approx(0.9457159069)
    # the Bounds line must not be mistaken for control points
    assert georef.parse_tab_size(TAB_BAD) == (5287, 5000)


def test_detects_squeezed_only():
    assert georef.is_squeezed(georef.parse_tfw(TFW_BAD))
    assert not georef.is_squeezed(georef.parse_tfw(TFW_OK))


def profile(n, margin_left=0, margin_right=0):
    """Paper-fraction profile: margins white, map content not."""
    return [0.95 if i < margin_left or i >= n - margin_right else 0.02 for i in range(n)]


def test_best_offset_margin_left_right_both():
    assert georef.best_offset(profile(1236, margin_left=236), cell=1000)[0] == 236
    assert georef.best_offset(profile(1287, margin_right=287), cell=1000)[0] == 0
    k, gap = georef.best_offset(profile(1300, margin_left=100, margin_right=200), cell=1000)
    assert k == 100 and gap >= georef.CONFIDENT_GAP


def test_best_offset_unsure_when_margin_is_not_paper():
    k, gap = georef.best_offset([0.02] * 1300, cell=1000)
    assert gap < georef.CONFIDENT_GAP


def test_best_offset_exact_size():
    assert georef.best_offset([0.0] * 1000, cell=1000) == (0, float("inf"))


def test_known_offsets_from_checklist():
    assert georef.is_listed("133_10a0g79_0_b2")
    assert georef.known_offset("133_10a0g79_0_b2") == (236, 0)
    assert georef.known_offset("133_2d5j74_0_b2") == (0, 0)
    assert georef.known_offset("133_8a6g78_0_b2") == (402, 0)
    assert georef.known_offset("133_10a0j79_0_b2") is None  # listed, not yet verified
    assert not georef.is_listed("133_5h5c42_0_b2")


def test_layer_source_leaves_good_sheets_alone(tmp_path):
    (tmp_path / "a.tif").write_bytes(b"")
    (tmp_path / "a.tfw").write_text(TFW_OK)
    (tmp_path / "a.TAB").write_text(TAB_BAD.replace("5287", "5000"))
    assert georef.layer_source(tmp_path / "a.tif") == (str(tmp_path / "a.tif"), None)


def test_layer_source_measures_and_crops(tmp_path):
    np = pytest.importorskip("numpy")
    gdal = pytest.importorskip("osgeo.gdal")
    cell, width = 200, 260  # synthetic sheet: 60 px of white margin on the left
    img = np.full((3, cell, width), 40, dtype=np.uint8)
    img[:, :, :60] = 255
    path = tmp_path / "133_9z9z99_0_b2.tif"
    ds = gdal.GetDriverByName("GTiff").Create(str(path), width, cell, 3, gdal.GDT_Byte)
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(img[i])
    ds = None
    pixel = cell / width
    path.with_suffix(".tfw").write_text(f"{pixel}\n0\n0\n-1\n{1000 + pixel / 2}\n{5000 - 0.5}\n")
    path.with_suffix(".TAB").write_text(
        f'(1000,5000) (0,0) Label "Pt 1",\n(1200,5000) ({width},0) Label "Pt 2",\n'
        f'(1000,4800) (0,{cell}) Label "Pt 3"\n'
    )
    vrt, status = georef.layer_source(path, cell=cell)
    assert status == georef.MEASURED and vrt.endswith("_fixed.vrt")
    out = gdal.Open(vrt)
    assert (out.RasterXSize, out.RasterYSize) == (cell, cell)
    assert out.GetGeoTransform()[:2] == pytest.approx((1000.0, 1.0))
    assert out.GetRasterBand(1).ReadAsArray().max() == 40  # margin cropped away
