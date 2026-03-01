"""Tests for scripts/parse_layout.py — HTML layout parsing."""

import pytest

from scripts.parse_layout import (
    _find_col,
    _parse_int,
    _positional_fallback,
    parse_layout_html,
)


# ─── _parse_int ───────────────────────────────────────────────────────────────

def test_parse_int_normal():
    assert _parse_int("42") == 42


def test_parse_int_with_comma():
    assert _parse_int("1,234") == 1234


def test_parse_int_with_spaces():
    assert _parse_int("  7  ") == 7


def test_parse_int_invalid():
    assert _parse_int("N/A") is None


def test_parse_int_empty():
    assert _parse_int("") is None


# ─── _find_col ────────────────────────────────────────────────────────────────

def test_find_col_exact_match():
    assert _find_col(["variable name", "label", "start"], ["variable name"]) == 0


def test_find_col_partial_match():
    # "variable name" as a substring of a longer header string
    assert _find_col(["the variable name here", "label", "start"], ["variable name"]) == 0


def test_find_col_first_candidate_wins():
    # "variable label" appears before "label" in candidates, and header[0] has it
    assert _find_col(["variable label", "start", "length"], ["variable label", "label"]) == 0


def test_find_col_falls_through_to_second_candidate():
    assert _find_col(["var", "field length", "start"], ["field length", "length"]) == 1


def test_find_col_not_found():
    assert _find_col(["a", "b", "c"], ["nonexistent"]) is None


# ─── _positional_fallback ─────────────────────────────────────────────────────

def test_positional_fallback_5_cols():
    assert _positional_fallback(["a", "b", "c", "d", "e"]) == (0, 1, 2, 3, 4)


def test_positional_fallback_4_cols():
    assert _positional_fallback(["a", "b", "c", "d"]) == (0, 1, None, 2, 3)


def test_positional_fallback_3_cols():
    assert _positional_fallback(["a", "b", "c"]) == (0, None, None, 1, 2)


def test_positional_fallback_2_cols():
    col_var, col_label, col_section, col_start, col_length = _positional_fallback(["a", "b"])
    assert col_var == 0
    assert col_start == 1


# ─── parse_layout_html ────────────────────────────────────────────────────────

def _write_html(tmp_path, name, html):
    p = tmp_path / name
    p.write_text(html, encoding="utf-8")
    return p


FULL_5COL_HTML = """\
<html><body><table>
  <tr>
    <th>Variable Name</th>
    <th>Variable Label</th>
    <th>Section</th>
    <th>Start</th>
    <th>Length</th>
  </tr>
  <tr>
    <td>GENHLTH</td>
    <td>General Health</td>
    <td>Health Status</td>
    <td>70</td>
    <td>1</td>
  </tr>
  <tr>
    <td>_STATE</td>
    <td>State FIPS Code</td>
    <td>Interview Admin</td>
    <td>1</td>
    <td>2</td>
  </tr>
</table></body></html>
"""

THREE_COL_HTML = """\
<html><body><table>
  <tr>
    <th>col1</th>
    <th>col2</th>
    <th>col3</th>
  </tr>
  <tr>
    <td>GENHLTH</td>
    <td>70</td>
    <td>1</td>
  </tr>
  <tr>
    <td>EXERANY2</td>
    <td>120</td>
    <td>1</td>
  </tr>
</table></body></html>
"""


def test_parse_layout_html_full_5col(tmp_path):
    p = _write_html(tmp_path, "layout.html", FULL_5COL_HTML)
    result = parse_layout_html(p)

    assert len(result) == 2

    genhlth = result[0]
    assert genhlth["var"] == "GENHLTH"
    assert genhlth["label"] == "General Health"
    assert genhlth["section"] == "Health Status"
    assert genhlth["start"] == 70
    assert genhlth["length"] == 1

    state = result[1]
    assert state["var"] == "_STATE"
    assert state["start"] == 1
    assert state["length"] == 2


def test_parse_layout_html_3col_positional_fallback(tmp_path):
    """Generic 3-col headers trigger positional fallback: var|start|length."""
    p = _write_html(tmp_path, "layout3.html", THREE_COL_HTML)
    result = parse_layout_html(p)

    assert len(result) == 2
    assert result[0]["var"] == "GENHLTH"
    assert result[0]["start"] == 70
    assert result[0]["length"] == 1
    assert result[1]["var"] == "EXERANY2"


def test_parse_layout_html_skips_invalid_var_names(tmp_path):
    html = """\
<html><body><table>
  <tr><th>Variable Name</th><th>Label</th><th>Start</th><th>Length</th></tr>
  <tr><td>GOODVAR</td><td>A label</td><td>1</td><td>1</td></tr>
  <tr><td>123BAD</td><td>Starts with digit</td><td>2</td><td>1</td></tr>
  <tr><td></td><td>Empty name</td><td>3</td><td>1</td></tr>
  <tr><td>HAS SPACE</td><td>Space in name</td><td>4</td><td>1</td></tr>
</table></body></html>
"""
    p = _write_html(tmp_path, "layout_invalid.html", html)
    result = parse_layout_html(p)
    assert len(result) == 1
    assert result[0]["var"] == "GOODVAR"


def test_parse_layout_html_skips_unparseable_start_or_length(tmp_path):
    html = """\
<html><body><table>
  <tr><th>Variable Name</th><th>Label</th><th>Start</th><th>Length</th></tr>
  <tr><td>GOODVAR</td><td>Label</td><td>10</td><td>2</td></tr>
  <tr><td>BADSTART</td><td>Label</td><td>N/A</td><td>1</td></tr>
  <tr><td>BADLEN</td><td>Label</td><td>5</td><td></td></tr>
</table></body></html>
"""
    p = _write_html(tmp_path, "layout_badnums.html", html)
    result = parse_layout_html(p)
    assert len(result) == 1
    assert result[0]["var"] == "GOODVAR"


def test_parse_layout_html_no_label_or_section(tmp_path):
    """Variables without label/section should be returned without those keys."""
    html = """\
<html><body><table>
  <tr><th>Variable Name</th><th>Start</th><th>Length</th></tr>
  <tr><td>AVAR</td><td>5</td><td>1</td></tr>
</table></body></html>
"""
    p = _write_html(tmp_path, "layout_min.html", html)
    result = parse_layout_html(p)
    assert len(result) == 1
    assert result[0]["var"] == "AVAR"
    assert "label" not in result[0]
    assert "section" not in result[0]


def test_parse_layout_html_no_tables_raises(tmp_path):
    p = _write_html(tmp_path, "empty.html", "<html><body><p>no table here</p></body></html>")
    with pytest.raises(ValueError, match="No tables"):
        parse_layout_html(p)


def test_parse_layout_html_largest_table_chosen(tmp_path):
    """The table with the most rows should be used when multiple tables exist."""
    html = """\
<html><body>
  <table><tr><td>nav</td></tr></table>
  <table>
    <tr><th>Variable Name</th><th>Label</th><th>Start</th><th>Length</th></tr>
    <tr><td>VAR1</td><td>First</td><td>1</td><td>1</td></tr>
    <tr><td>VAR2</td><td>Second</td><td>2</td><td>1</td></tr>
  </table>
</body></html>
"""
    p = _write_html(tmp_path, "multi_table.html", html)
    result = parse_layout_html(p)
    assert len(result) == 2
    assert result[0]["var"] == "VAR1"
