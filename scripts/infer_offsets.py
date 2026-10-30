"""Fill ``inferred_offset`` in data/nonstandard_sheets.csv from which neighbour sheets exist.

Lantmäteriet enlarged some sheets instead of making a new sheet for a tiny strip of land,
so a sheet that is larger than its grid cell has no neighbour sheet on the side where it was
enlarged. For each oversized edition and axis: if exactly one of the two neighbours across
that axis has a map, the enlargement is on the other side. Both or neither -> ambiguous, left
empty (the plugin then measures it from the image).

``inferred_offset`` is "kx,ky": pixels of enlargement left of / above the grid cell.
Needs network access (anonymous FTP listing of every block, about two minutes).
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ekonomiska_kartan import ftpindex, grid  # noqa: E402

DATA = ROOT / "ekonomiska_kartan" / "data" / "nonstandard_sheets.csv"


def sheets_with_map():
    ftp = ftpindex.connect()
    lines = []
    ftp.retrlines(f"LIST {ftpindex.ROOT}", lines.append)
    blocks = sorted(ftpindex.parse_list_line(line)[0] for line in lines)
    have = set()
    for block in blocks:
        for ruta, eds in ftpindex.list_block(ftp, block).items():
            if any("tif" in e.files for e in eds):
                have.add(ruta)
    ftp.close()
    return have


def neighbour_exists(have, x, y):
    try:
        return grid.ruta_at(x, y) in have
    except (ValueError, OverflowError):
        return False


def infer(have, ruta, extra_w, extra_h):
    """(kx, ky) or None when the side cannot be told from the neighbours."""
    xmin, ymin, xmax, ymax = grid.ruta_bounds(ruta)
    xmid, ymid = (xmin + xmax) // 2, (ymin + ymax) // 2
    kx = ky = 0
    if extra_w:
        west = neighbour_exists(have, xmin - 1, ymid)
        east = neighbour_exists(have, xmax + 1, ymid)
        if west == east:
            return None
        kx = extra_w if east else 0  # enlarged towards the side without a neighbour
    if extra_h:
        north = neighbour_exists(have, xmid, ymax + 1)
        south = neighbour_exists(have, xmid, ymin - 1)
        if north == south:
            return None
        ky = extra_h if south else 0
    return kx, ky


def main():
    have = sheets_with_map()
    print(len(have), "sheets with a map on the server")
    with open(DATA, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames)
        rows = list(reader)
    if "inferred_offset" not in fields:
        fields.insert(fields.index("verified_offset"), "inferred_offset")
    solved = agree = disagree = 0
    for row in rows:
        result = None
        if row["ruta"] not in grid.IRREGULAR:
            result = infer(have, row["ruta"], int(row["extra_w_px"]), int(row["extra_h_px"]))
        row["inferred_offset"] = f"{result[0]},{result[1]}" if result else ""
        solved += result is not None
        if result and row["verified_offset"]:
            same = row["verified_offset"] == row["inferred_offset"]
            agree += same
            disagree += not same
            print("verified", row["stem"], row["verified_offset"], "inferred",
                  row["inferred_offset"], "OK" if same else "DIFFERENT")
    with open(DATA, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"inferred {solved} of {len(rows)}; verified rows: {agree} agree, {disagree} differ")


if __name__ == "__main__":
    main()
