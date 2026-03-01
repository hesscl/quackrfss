"""Tests for scripts/parse_sasout.py — sasout SAS DATA step parsing."""

from scripts.parse_sasout import parse_sasout, _extract_mappings


# ─── basic extraction ─────────────────────────────────────────────────────────

def test_parse_basic():
    sas = """
DATA brfss;
  LABEL GENHLTH = 'GENERAL HEALTH';
   /*          1 = 'EXCELLENT'
               2 = 'VERY GOOD'
               3 = 'GOOD'
               4 = 'FAIR'
               5 = 'POOR'
               7 = 'DO NOT KNOW'
               9 = 'REFUSED' */;
RUN;
"""
    result = parse_sasout(sas)
    assert "GENHLTH" in result
    assert result["GENHLTH"]["1"] == "EXCELLENT"
    assert result["GENHLTH"]["2"] == "VERY GOOD"
    assert result["GENHLTH"]["9"] == "REFUSED"


def test_parse_multiple_variables():
    sas = """
  LABEL HLTHPLAN = 'HAVE ANY KIND OF HEALTH PLAN';
   /*          1 = 'YES'
               2 = 'NO'
               7 = 'DO NOT KNOW'
               9 = 'REFUSED' */;

  LABEL SEX = 'SEX OF RESPONDENT';
   /*          1 = 'MALE'
               2 = 'FEMALE' */;
"""
    result = parse_sasout(sas)
    assert "HLTHPLAN" in result
    assert "SEX" in result
    assert result["HLTHPLAN"]["1"] == "YES"
    assert result["SEX"]["2"] == "FEMALE"


# ─── code normalisation ───────────────────────────────────────────────────────

def test_leading_zeros_stripped():
    """Codes like 01, 02 should be stored as '1', '2' to match load.py _val_key."""
    sas = """
  LABEL DISPCODE = 'FINAL DISPOSITION';
   /*         01 = 'COMPLETED INTERVIEW'
              02 = 'REFUSED INTERVIEW'
              11 = 'CALLBACK NEEDED' */;
"""
    result = parse_sasout(sas)
    assert "DISPCODE" in result
    assert "1" in result["DISPCODE"]
    assert "2" in result["DISPCODE"]
    assert "11" in result["DISPCODE"]
    assert "01" not in result["DISPCODE"]
    assert result["DISPCODE"]["1"] == "COMPLETED INTERVIEW"


# ─── label without comment block is skipped ──────────────────────────────────

def test_label_without_comment_skipped():
    """Variables with only a description and no value mappings should not appear."""
    sas = """
  LABEL _STATE = 'STATE FIPS CODE';
  LABEL GENHLTH = 'GENERAL HEALTH';
   /*    1 = 'EXCELLENT'
         9 = 'REFUSED' */;
"""
    result = parse_sasout(sas)
    assert "_STATE" not in result
    assert "GENHLTH" in result


# ─── case insensitivity ───────────────────────────────────────────────────────

def test_label_keyword_case_insensitive():
    sas = """
  label SMOKER = 'SMOKER STATUS';
   /*    1 = 'CURRENT'
         2 = 'FORMER'
         3 = 'NEVER' */;
"""
    result = parse_sasout(sas)
    assert "SMOKER" in result
    assert result["SMOKER"]["1"] == "CURRENT"


def test_varname_uppercased():
    sas = """
  LABEL genhlth = 'GENERAL HEALTH';
   /*    1 = 'EXCELLENT' */;
"""
    result = parse_sasout(sas)
    assert "GENHLTH" in result
    assert "genhlth" not in result


# ─── double-quoted labels ─────────────────────────────────────────────────────

def test_double_quoted_label():
    sas = """
  LABEL FOO = "SOME VARIABLE";
   /*    1 = "YES"
         2 = "NO" */;
"""
    result = parse_sasout(sas)
    assert "FOO" in result
    assert result["FOO"]["1"] == "YES"


# ─── edge cases ───────────────────────────────────────────────────────────────

def test_empty_string():
    assert parse_sasout("") == {}


def test_no_comment_blocks():
    sas = """
DATA brfss;
  LABEL _STATE = 'STATE FIPS CODE';
  LABEL AGE = 'AGE OF RESPONDENT';
RUN;
"""
    assert parse_sasout(sas) == {}


def test_comment_without_mappings_skipped():
    """A comment that contains no integer = 'label' lines should not add the variable."""
    sas = """
  LABEL IDATE = 'INTERVIEW DATE';
   /* See codebook for date format details */;
"""
    result = parse_sasout(sas)
    assert "IDATE" not in result


# ─── 1990–1993: unquoted description + block comment ─────────────────────────

def test_unquoted_description_block_comment():
    """1990–1993 style: LABEL VARNAME = UNQUOTED DESC\n /* ... */"""
    sas = """
LABEL GENHLTH = GENERAL HEALTH
 /*          1 = 'EXCELLENT'
             2 = 'VERY GOOD'
             3 = 'GOOD'
             9 = 'REFUSED' */;
"""
    result = parse_sasout(sas)
    assert "GENHLTH" in result
    assert result["GENHLTH"]["1"] == "EXCELLENT"
    assert result["GENHLTH"]["9"] == "REFUSED"


def test_unquoted_description_multiple_vars():
    sas = """
LABEL GENHLTH = GENERAL HEALTH
 /*    1 = 'EXCELLENT'
       9 = 'REFUSED' */;

LABEL SEX = SEX OF RESPONDENT
 /*    1 = 'MALE'
       2 = 'FEMALE' */;
"""
    result = parse_sasout(sas)
    assert "GENHLTH" in result
    assert "SEX" in result
    assert result["SEX"]["1"] == "MALE"


# ─── 1994: quoted description + star comment ─────────────────────────────────

def test_star_comment_style():
    """1994 style: LABEL VARNAME = 'desc';\n * N = 'label' *\n ...;"""
    sas = """
LABEL GENHLTH  = 'GENERAL HEALTH';
*********************
* 1 = 'EXCELLENT'   *
* 2 = 'VERY GOOD'   *
* 3 = 'GOOD'        *
* 9 = 'REFUSED'     *
*********************;
"""
    result = parse_sasout(sas)
    assert "GENHLTH" in result
    assert result["GENHLTH"]["1"] == "EXCELLENT"
    assert result["GENHLTH"]["3"] == "GOOD"
    assert result["GENHLTH"]["9"] == "REFUSED"


def test_star_comment_multiple_vars():
    sas = """
LABEL HLTHPLAN = 'HAVE ANY KIND OF HEALTH PLAN';
*********************
* 1 = 'YES'         *
* 2 = 'NO'          *
* 9 = 'REFUSED'     *
*********************;

LABEL CHECKUP = 'HOW LONG SINCE LAST ROUTINE CHECKUP';
********************************
* 1 = 'WITHIN PAST YEAR'       *
* 2 = 'WITHIN PAST TWO YEARS'  *
* 8 = 'NEVER'                  *
********************************;
"""
    result = parse_sasout(sas)
    assert "HLTHPLAN" in result
    assert "CHECKUP" in result
    assert result["HLTHPLAN"]["1"] == "YES"
    assert result["CHECKUP"]["8"] == "NEVER"


def test_star_comment_leading_zeros_stripped():
    sas = """
LABEL DISPCODE = 'FINAL DISPOSITION';
***************************
* 01 = 'COMPLETED'        *
* 02 = 'REFUSED'          *
* 11 = 'CALLBACK NEEDED'  *
***************************;
"""
    result = parse_sasout(sas)
    assert "DISPCODE" in result
    assert "1" in result["DISPCODE"]
    assert "01" not in result["DISPCODE"]
    assert result["DISPCODE"]["11"] == "CALLBACK NEEDED"
