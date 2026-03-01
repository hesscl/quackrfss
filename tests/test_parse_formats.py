"""Tests for scripts/parse_formats.py — SAS FORMAT parsing."""

from scripts.parse_formats import _normalise_format_name, parse_format_sas


# ─── _normalise_format_name ───────────────────────────────────────────────────

def test_normalise_strips_dollar_prefix():
    assert _normalise_format_name("$STATE") == "STATE"


def test_normalise_uppercases():
    assert _normalise_format_name("genhlth") == "GENHLTH"


def test_normalise_dollar_and_lowercase():
    assert _normalise_format_name("$sstate") == "SSTATE"


def test_normalise_no_prefix():
    assert _normalise_format_name("SEXVAR") == "SEXVAR"


def test_normalise_strips_only_leading_dollar():
    # Internal $ should be left alone (edge case)
    assert _normalise_format_name("$ST$ATE") == "ST$ATE"


# ─── parse_format_sas ─────────────────────────────────────────────────────────

def test_parse_basic_value_block():
    sas = """
PROC FORMAT;
  VALUE GENHLTH
    1 = 'Excellent'
    2 = 'Very good'
    3 = 'Good'
    9 = 'Refused'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "GENHLTH" in result
    assert result["GENHLTH"]["1"] == "Excellent"
    assert result["GENHLTH"]["2"] == "Very good"
    assert result["GENHLTH"]["9"] == "Refused"


def test_parse_multiple_blocks():
    sas = """
PROC FORMAT;
  VALUE SEX
    1 = 'Male'
    2 = 'Female'
  ;
  VALUE YESNO
    1 = 'Yes'
    2 = 'No'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "SEX" in result
    assert "YESNO" in result
    assert result["SEX"]["1"] == "Male"
    assert result["YESNO"]["2"] == "No"


def test_parse_short_range_expands():
    """Ranges of ≤20 values should be expanded to individual string keys."""
    sas = """
PROC FORMAT;
  VALUE MCODE
    1-3 = 'Low'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "MCODE" in result
    assert result["MCODE"]["1"] == "Low"
    assert result["MCODE"]["2"] == "Low"
    assert result["MCODE"]["3"] == "Low"
    assert len(result["MCODE"]) == 3


def test_parse_long_range_stays_as_string():
    """Ranges >20 values should be kept as a range string, not expanded."""
    sas = """
PROC FORMAT;
  VALUE BIGRANGE
    100-200 = 'Many'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "BIGRANGE" in result
    assert "100-200" in result["BIGRANGE"]
    assert result["BIGRANGE"]["100-200"] == "Many"
    # Should NOT have been expanded to 101 individual keys
    assert len(result["BIGRANGE"]) == 1


def test_parse_exact_boundary_range_expands():
    """A range of exactly 20 values (hi - lo == 20) should expand."""
    sas = """
PROC FORMAT;
  VALUE BOUNDARY
    1-21 = 'Edge'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "BOUNDARY" in result
    assert len(result["BOUNDARY"]) == 21  # 1 through 21 inclusive


def test_parse_comma_list():
    sas = """
PROC FORMAT;
  VALUE COMBO
    1,2,3 = 'Low group'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "COMBO" in result
    assert result["COMBO"]["1"] == "Low group"
    assert result["COMBO"]["2"] == "Low group"
    assert result["COMBO"]["3"] == "Low group"


def test_parse_other_keyword():
    sas = """
PROC FORMAT;
  VALUE MYVAR
    1 = 'Known'
    OTHER = 'Unknown'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "MYVAR" in result
    assert result["MYVAR"]["1"] == "Known"
    assert result["MYVAR"]["OTHER"] == "Unknown"


def test_parse_dollar_prefix_format():
    """Character formats with $ prefix should have $ stripped from the key."""
    sas = """
PROC FORMAT;
  VALUE $STATEF
    '01' = 'Alabama'
    '02' = 'Alaska'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "STATEF" in result
    assert result["STATEF"]["01"] == "Alabama"
    assert result["STATEF"]["02"] == "Alaska"


def test_parse_double_quoted_labels():
    sas = """
PROC FORMAT;
  VALUE DQTEST
    1 = "Yes"
    2 = "No"
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "DQTEST" in result
    assert result["DQTEST"]["1"] == "Yes"
    assert result["DQTEST"]["2"] == "No"


def test_parse_empty_string():
    assert parse_format_sas("") == {}


def test_parse_no_value_blocks():
    assert parse_format_sas("DATA step;\n  x = 1;\nRUN;\n") == {}


def test_parse_case_insensitive_value_keyword():
    """VALUE keyword matching should be case-insensitive."""
    sas = """
PROC FORMAT;
  value lowcase
    1 = 'One'
  ;
RUN;
"""
    result = parse_format_sas(sas)
    assert "LOWCASE" in result
    assert result["LOWCASE"]["1"] == "One"
