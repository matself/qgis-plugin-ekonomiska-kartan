"""Detect a GeoTIFF that holds no image data (pure Python, no QGIS imports).

A few sheets on the server, e.g. 3d9e, are tifs whose tile table is empty: every tile has
offset 0 and byte count 0, so GDAL and QGIS show a plain black image. Only the file's
directory is read (a few KB), not the pixels.
"""
import struct

TILE_BYTE_COUNTS, STRIP_BYTE_COUNTS = 325, 279
SHORT, LONG = 3, 4
SIZES = {SHORT: ("H", 2), LONG: ("I", 4)}


def _values(f, order, kind, count, raw):
    code, size = SIZES[kind]
    if size * count <= 4:
        return struct.unpack(f"{order}{count}{code}", raw[: size * count])
    (offset,) = struct.unpack(order + "I", raw)
    f.seek(offset)
    return struct.unpack(f"{order}{count}{code}", f.read(size * count))


def is_empty(path):
    """True if the (classic) TIFF lists its image data but every piece has byte count 0."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            order = {b"II": "<", b"MM": ">"}.get(head[:2])
            if order is None:
                return False
            magic, ifd = struct.unpack(order + "HI", head[2:8])
            if magic != 42:  # not a classic TIFF (BigTIFF etc.): leave it alone
                return False
            f.seek(ifd)
            (count,) = struct.unpack(order + "H", f.read(2))
            entries = f.read(12 * count)
            counts = {}
            for i in range(count):
                tag, kind, n = struct.unpack_from(order + "HHI", entries, 12 * i)
                if tag in (TILE_BYTE_COUNTS, STRIP_BYTE_COUNTS) and kind in SIZES:
                    start = 12 * i + 8
                    raw = entries[start:start + 4]
                    counts[tag] = _values(f, order, kind, n, raw)
    except (OSError, struct.error):
        return False
    pieces = counts.get(TILE_BYTE_COUNTS) or counts.get(STRIP_BYTE_COUNTS)
    return bool(pieces) and not any(pieces)
