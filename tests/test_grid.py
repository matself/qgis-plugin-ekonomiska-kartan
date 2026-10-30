"""Grid maths. The full check against EkoRutor.shp runs when EKORUTOR_SHP is set."""
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekonomiska_kartan import grid  # noqa: E402


def test_bounds_roundtrip():
    assert grid.ruta_bounds("10a3g") == (1_230_000, 6_565_000, 1_235_000, 6_570_000)
    for name in ("1a0a", "10a3g", "27n9j", "4d1d"):
        xmin, ymin, xmax, ymax = grid.ruta_bounds(name)
        assert grid.ruta_at(xmin, ymin) == name
        assert grid.ruta_at(xmax - 1, ymax - 1) == name


def test_storruta():
    assert grid.storruta("10a3g") == "10a"
    assert grid.storrutor(["10a3g", "10a0a", "4d1d"]) == ["10a", "4d"]


def test_bbox_cover():
    x, y, _, _ = grid.ruta_bounds("10a3g")
    # inside one sheet
    assert grid.rutor_in_bbox(x + 10, y + 10, x + 20, y + 20) == ["10a3g"]
    # exactly one sheet: touching edges do not pull in neighbours
    assert grid.rutor_in_bbox(x, y, x + 5000, y + 5000) == ["10a3g"]
    # 2x2
    assert len(grid.rutor_in_bbox(x + 1, y + 1, x + 5001, y + 5001)) == 4


def _read_shp_bboxes(path):
    data = Path(path).read_bytes()
    pos = 100
    while pos < len(data):
        _, length = struct.unpack(">ii", data[pos : pos + 8])
        shape_type = struct.unpack("<i", data[pos + 8 : pos + 12])[0]
        if shape_type in (5, 15, 25):
            yield struct.unpack("<4d", data[pos + 12 : pos + 44])
        pos += 8 + length * 2


@pytest.mark.skipif("EKORUTOR_SHP" not in os.environ, reason="EKORUTOR_SHP not set")
def test_against_shapefile():
    bboxes = list(_read_shp_bboxes(os.environ["EKORUTOR_SHP"]))
    assert len(bboxes) == 12_015
    mismatches = [
        b for b in bboxes
        if grid.ruta_bounds(grid.ruta_at((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
        != tuple(round(v) for v in b)
    ]
    assert len(mismatches) <= len(grid.IRREGULAR)


def test_bbox_clipped_to_grid():
    assert grid.rutor_in_bbox(0, 0, 100, 100) == []  # entirely off-grid
    assert grid.count_in_bbox(1_200_000, 6_100_000, 1_210_000, 6_110_000) == 4
    everything = grid.count_in_bbox(1_200_000, 6_100_000, 9_000_000, 9_000_000)
    assert everything == grid.N_COLS * grid.N_ROWS


def test_blocks():
    assert grid.storruta_bounds("10a") == (1_200_000, 6_550_000, 1_250_000, 6_600_000)
    assert grid.storrutor_in_bbox(1_200_000, 6_550_000, 1_260_000, 6_560_000) == ["10a", "10b"]
