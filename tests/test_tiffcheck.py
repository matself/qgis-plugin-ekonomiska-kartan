import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekonomiska_kartan.tiffcheck import is_empty  # noqa: E402

REAL_3D9E = Path(__file__).parent / "data" / "empty_3d9e_header.tif"


def make_tiff(path, byte_counts, tag=325, order="<", kind=4):
    """A classic TIFF with one directory that has a byte-count tag (data itself not needed)."""
    code, size = {3: ("H", 2), 4: ("I", 4)}[kind]
    n = len(byte_counts)
    inline = size * n <= 4
    ifd_size = 2 + 12 + 4
    value = struct.pack(f"{order}{n}{code}", *byte_counts)
    field = value.ljust(4, b"\0") if inline else struct.pack(order + "I", 8 + ifd_size)
    ifd = struct.pack(order + "H", 1) + struct.pack(order + "HHI", tag, kind, n) + field
    ifd += struct.pack(order + "I", 0)
    head = (b"II" if order == "<" else b"MM") + struct.pack(order + "HI", 42, 8)
    path.write_bytes(head + ifd + (b"" if inline else value))
    return path


def test_all_zero_tiles_is_empty(tmp_path):
    assert is_empty(make_tiff(tmp_path / "a.tif", [0] * 300))


def test_tiles_with_data_is_not_empty(tmp_path):
    assert not is_empty(make_tiff(tmp_path / "a.tif", [0] * 299 + [1234]))
    assert not is_empty(make_tiff(tmp_path / "b.tif", [150_000] * 300))


def test_strips_and_short_counts_and_big_endian(tmp_path):
    assert is_empty(make_tiff(tmp_path / "a.tif", [0] * 40, tag=279, kind=3))
    assert is_empty(make_tiff(tmp_path / "b.tif", [0] * 40, order=">"))
    assert not is_empty(make_tiff(tmp_path / "c.tif", [7] * 40, tag=279, kind=3, order=">"))


def test_inline_counts(tmp_path):
    assert is_empty(make_tiff(tmp_path / "a.tif", [0]))
    assert not is_empty(make_tiff(tmp_path / "b.tif", [5]))


def test_not_a_tiff_or_unreadable_is_not_empty(tmp_path):
    junk = tmp_path / "junk.tif"
    junk.write_bytes(b"not a tiff at all")
    assert not is_empty(junk)
    assert not is_empty(tmp_path / "missing.tif")
    short = tmp_path / "short.tif"
    short.write_bytes(b"II*\0")
    assert not is_empty(short)
    big = tmp_path / "big.tif"
    big.write_bytes(b"II" + struct.pack("<HHHQ", 43, 8, 0, 16) + b"\0" * 32)
    assert not is_empty(big)  # BigTIFF is left alone


def test_real_header_of_the_empty_sheet_3d9e():
    """First 3 KB of 133_3d9e76_0_b2.tif from Lantmäteriet: directory with an empty tile table."""
    assert is_empty(REAL_3D9E)
