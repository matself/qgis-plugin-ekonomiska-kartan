"""Neighbour rule behind inferred_offset (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from infer_offsets import infer  # noqa: E402

AROUND_3G6H = {"3g6g", "3g6i", "3g7h"}  # west, east, north; nothing south


def test_enlarged_towards_the_side_without_a_neighbour():
    assert infer(AROUND_3G6H, "3g6h", 0, 404) == (0, 0)  # south: cell at the top
    assert infer(AROUND_3G6H - {"3g7h"} | {"3g5h"}, "3g6h", 0, 404) == (0, 404)  # north
    assert infer(AROUND_3G6H - {"3g6i"}, "3g6h", 300, 0) == (0, 0)  # east: cell at the left
    assert infer(AROUND_3G6H - {"3g6g"}, "3g6h", 300, 0) == (300, 0)  # west


def test_ambiguous_when_both_or_neither_neighbour_exists():
    assert infer(AROUND_3G6H | {"3g5h"}, "3g6h", 0, 404) is None
    assert infer(set(), "3g6h", 0, 404) is None
