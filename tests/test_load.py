"""Tests for scripts/load.py — label resolution and lookup building."""

from scripts.load import _NULL_CODES, _build_label_lookup, _resolve_format_name


# ─── _resolve_format_name ─────────────────────────────────────────────────────

def test_resolve_direct_match():
    labels = {"GENHLTH": {"1": "Excellent"}, "SEXVAR": {"1": "Male"}}
    assert _resolve_format_name("GENHLTH", labels) == "GENHLTH"


def test_resolve_s_prefix_mapping():
    """_STATE (underscore prefix) should resolve to SSTATE in labels dict."""
    labels = {"SSTATE": {"1": "Alabama"}}
    assert _resolve_format_name("_STATE", labels) == "SSTATE"


def test_resolve_underscore_col_direct_match():
    """_RFBMI5 maps directly when labels uses the underscore name."""
    labels = {"_RFBMI5": {"1": "Normal weight"}}
    assert _resolve_format_name("_RFBMI5", labels) == "_RFBMI5"


def test_resolve_underscore_col_direct_beats_s_prefix():
    """Direct match takes priority over S-prefix fallback."""
    labels = {"_RFBMI5": {"1": "Direct"}, "SRFBMI5": {"1": "S-prefix"}}
    assert _resolve_format_name("_RFBMI5", labels) == "_RFBMI5"


def test_resolve_not_found():
    labels = {"GENHLTH": {"1": "Excellent"}}
    assert _resolve_format_name("EXERANY2", labels) is None


def test_resolve_s_prefix_also_not_found():
    """_VARNAME where neither _VARNAME nor SVARNAME is in labels → None."""
    labels = {"GENHLTH": {"1": "Excellent"}}
    assert _resolve_format_name("_VARNAME", labels) is None


def test_resolve_non_underscore_col_no_s_fallback():
    """Only columns starting with _ trigger the S-prefix fallback."""
    labels = {"SSEXVAR": {"1": "Male"}}
    assert _resolve_format_name("SEXVAR", labels) is None


# ─── _build_label_lookup ──────────────────────────────────────────────────────

def test_build_label_lookup_normal_values_pass_through():
    raw = {"GENHLTH": {"1": "Excellent", "2": "Very good", "3": "Good"}}
    result = _build_label_lookup(raw)
    assert result["GENHLTH"]["1"] == "Excellent"
    assert result["GENHLTH"]["2"] == "Very good"
    assert result["GENHLTH"]["3"] == "Good"


def test_build_label_lookup_sentinels_become_none():
    raw = {"GENHLTH": {"1": "Excellent", "7": "Don't know", "9": "Refused"}}
    result = _build_label_lookup(raw)
    assert result["GENHLTH"]["1"] == "Excellent"
    assert result["GENHLTH"]["7"] is None
    assert result["GENHLTH"]["9"] is None


def test_build_label_lookup_all_null_codes():
    """Every code in _NULL_CODES should map to None."""
    raw = {"VAR": {code: f"label for {code}" for code in _NULL_CODES}}
    result = _build_label_lookup(raw)
    for code in _NULL_CODES:
        assert result["VAR"][code] is None, f"Expected {code!r} → None"


def test_build_label_lookup_blank_sentinel():
    raw = {"VAR": {"BLANK": "Missing data"}}
    result = _build_label_lookup(raw)
    assert result["VAR"]["BLANK"] is None


def test_build_label_lookup_multi_digit_sentinels():
    """77, 777, 99, 999, etc. are all sentinel codes."""
    raw = {"VAR": {"1": "Real", "77": "Refused", "99": "Unknown", "999": "Missing"}}
    result = _build_label_lookup(raw)
    assert result["VAR"]["1"] == "Real"
    assert result["VAR"]["77"] is None
    assert result["VAR"]["99"] is None
    assert result["VAR"]["999"] is None


def test_build_label_lookup_multiple_vars():
    raw = {
        "GENHLTH": {"1": "Excellent", "9": "Refused"},
        "SEX": {"1": "Male", "2": "Female", "7": "Don't know"},
    }
    result = _build_label_lookup(raw)
    assert result["GENHLTH"]["1"] == "Excellent"
    assert result["GENHLTH"]["9"] is None
    assert result["SEX"]["1"] == "Male"
    assert result["SEX"]["7"] is None


def test_build_label_lookup_empty_input():
    assert _build_label_lookup({}) == {}


def test_build_label_lookup_empty_var_mapping():
    raw = {"VAR": {}}
    result = _build_label_lookup(raw)
    assert result["VAR"] == {}
