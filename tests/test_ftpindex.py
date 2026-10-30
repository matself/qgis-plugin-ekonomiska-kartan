import ftplib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ekonomiska_kartan import ftpindex  # noqa: E402

LISTING = [
    "-rw-r--r--   1 ftp ftp  50000000 Jan  1  2020 133_4d1d51_0_b2.tif",
    "-rw-r--r--   1 ftp ftp       100 Jan  1  2020 133_4d1d51_0_b2.tfw",
    "-rw-r--r--   1 ftp ftp  60000000 Jan  1  2020 133_4d1d85_0_b2.tif",
    "-rw-r--r--   1 ftp ftp       500 Jan  1  2020 133_4d1d85_0_b2.TAB",
    "-rw-r--r--   1 ftp ftp  45000000 Jan  1  2020 133_4d1d72_0_b2.tif",
    "-rw-r--r--   1 ftp ftp  45000000 Jan  1  2020 133_4d2a-1_0_b2.tif",
    "-rw-r--r--   1 ftp ftp  45000000 Jan  1  2020 133_4d2b_0_b2.tif",
    "-rw-r--r--   1 ftp ftp       100 Jan  1  2020 readme.txt",
]


def test_parse_filename():
    assert ftpindex.parse_filename("133_10a0g79_0_b2.tif") == (
        "10a0g", 79, "133_10a0g79_0_b2", "tif",
    )
    assert ftpindex.parse_filename("133_4d2b_0_b2.tif")[1] == -1
    assert ftpindex.parse_filename("133_4d2a-1_0_b2.tif")[1] == -1
    assert ftpindex.parse_filename("readme.txt") is None


def test_editions():
    res = ftpindex.editions_from_listing(LISTING, "/Ekonomiska_kartan/4d")
    assert set(res) == {"4d1d", "4d2a", "4d2b"}
    eds = res["4d1d"]
    assert [e.year for e in eds] == [51, 72, 85]
    best = ftpindex.latest(eds)
    assert best.year == 85 and best.tif_size == 60_000_000
    assert set(best.files) == {"tif", "tab"}
    assert ftpindex.remote_path(best, "tif") == "/Ekonomiska_kartan/4d/133_4d1d85_0_b2.tif"


class FakeFtp:
    def __init__(self, error=None):
        self.error = error

    def retrlines(self, command, callback):
        if self.error:
            raise self.error
        for line in LISTING:
            callback(line)


def test_missing_block_directory_is_empty():
    # the server has no directory for blocks without maps and answers 450
    error = ftplib.error_temp("450 /Ekonomiska_kartan/3h: No such file or directory")
    assert ftpindex.list_block(FakeFtp(error), "3h") == {}
    assert set(ftpindex.list_block(FakeFtp(), "4d")) == {"4d1d", "4d2a", "4d2b"}


def test_other_ftp_errors_still_raise():
    with pytest.raises(ftplib.error_temp):
        ftpindex.list_block(FakeFtp(ftplib.error_temp("421 Too many connections")), "4d")
