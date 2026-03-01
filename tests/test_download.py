"""Tests for scripts/download.py — URL-to-path resolution."""

from scripts.download import RAW_DIR, _dest_path


def test_dest_path_basic():
    p = _dest_path("2024", "/brfss/annual_2024_SAS/LLCP2024XPT.zip")
    assert p == RAW_DIR / "2024" / "LLCP2024XPT.zip"


def test_dest_path_uppercase_ext():
    """2012–2014 use uppercase .ZIP; filename case must be preserved."""
    p = _dest_path("2012", "/brfss/annual_2012_SAS/LLCP2012XPT.ZIP")
    assert p == RAW_DIR / "2012" / "LLCP2012XPT.ZIP"


def test_dest_path_nested_url():
    """Only the basename of the URL path is used."""
    p = _dest_path("2020", "/pub/brfss/annual_2020/deep/nested/LLCP2020XPT.zip")
    assert p == RAW_DIR / "2020" / "LLCP2020XPT.zip"


def test_dest_path_sas_format_file():
    p = _dest_path("2022", "/brfss/annual_2022_SAS/format22.sas")
    assert p == RAW_DIR / "2022" / "format22.sas"


def test_dest_path_cdbrfs_prefix():
    """2000–2010 use CDBRFS prefix instead of LLCP."""
    p = _dest_path("2006", "/brfss/annual_2006_SAS/CDBRFS06XPT.ZIP")
    assert p == RAW_DIR / "2006" / "CDBRFS06XPT.ZIP"


def test_dest_path_layout_html():
    p = _dest_path("2024", "/brfss/annual_2024_SAS/llcp_varlayout_24_onecolumn.html")
    assert p == RAW_DIR / "2024" / "llcp_varlayout_24_onecolumn.html"
