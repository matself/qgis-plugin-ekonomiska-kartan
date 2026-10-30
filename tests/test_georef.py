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
"""


def test_parse():
    assert georef.parse_tfw(TFW_BAD)[0] == pytest.approx(0.9457159069)
    assert georef.parse_tab_size(TAB_BAD) == (5287, 5000)


def test_detects_squeezed_only():
    assert georef.is_squeezed(georef.parse_tfw(TFW_BAD))
    assert not georef.is_squeezed(georef.parse_tfw(TFW_OK))


def test_corrected_keeps_corner_and_crops_margin():
    ulx, uly, cols, rows = georef.corrected(georef.parse_tfw(TFW_BAD), 5287, 5000)
    assert (ulx, uly) == pytest.approx((1395000.0, 6180000.0))
    assert (cols, rows) == (5000, 5000)


def test_layer_source_leaves_good_sheets_alone(tmp_path):
    (tmp_path / "a.tif").write_bytes(b"")
    (tmp_path / "a.tfw").write_text(TFW_OK)
    (tmp_path / "a.TAB").write_text(TAB_BAD.replace("5287", "5000"))
    assert georef.layer_source(tmp_path / "a.tif") == (str(tmp_path / "a.tif"), False)
