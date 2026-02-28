"""
Parse CDC BRFSS variable layout HTML pages into structured JSON.

The layout HTML contains a table with columns:
  Variable Name | Variable Label | Section | Start | Length

Output per year: metadata/layouts/{year}_layout.json
  [
    {"var": "GENHLTH", "label": "General Health", "section": "...", "start": 70, "length": 1},
    ...
  ]

Usage:
    python -m scripts.parse_layout              # all downloaded years
    python -m scripts.parse_layout --years 2023 2024
"""

import json
import re
from pathlib import Path

import click
from bs4 import BeautifulSoup
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
RAW_DIR = REPO_ROOT / "data" / "raw"
LAYOUTS_DIR = REPO_ROOT / "metadata" / "layouts"

console = Console()


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


def _layout_html_path(year: str, url_path: str) -> Path:
    filename = Path(url_path).name
    return RAW_DIR / year / filename


def _parse_int(val: str) -> int | None:
    val = val.strip().replace(",", "")
    try:
        return int(val)
    except ValueError:
        return None


def parse_layout_html(html_path: Path) -> list[dict]:
    """
    Parse the CDC variable layout HTML into a list of variable dicts.

    CDC pages vary slightly year to year; this handles the common patterns:
      - Table with th headers
      - Column order: Variable Name, Variable Label, Section (optional), Start, Length
    """
    with html_path.open(encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Find the main data table — it's the largest table on the page
    tables = soup.find_all("table")
    if not tables:
        raise ValueError(f"No tables found in {html_path}")

    # Pick the table with the most rows
    main_table = max(tables, key=lambda t: len(t.find_all("tr")))

    # Detect header row and column indices
    header_row = main_table.find("tr")
    if header_row is None:
        raise ValueError(f"No header row in {html_path}")

    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    col_var = _find_col(headers, ["variable name", "variable", "var name", "varname", "name"])
    col_label = _find_col(headers, ["variable label", "label", "description"])
    col_section = _find_col(headers, ["section", "questionnaire section"])
    col_start = _find_col(headers, ["start", "starting position", "position"])
    col_length = _find_col(headers, ["length", "field length", "len"])

    if col_var is None or col_start is None or col_length is None:
        # Fallback: some pages use positional columns without meaningful headers
        console.print(f"  [yellow]Headers: {headers} — using positional fallback[/yellow]")
        col_var, col_label, col_section, col_start, col_length = _positional_fallback(headers)

    variables = []
    for row in main_table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        def cell(idx: int | None) -> str:
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx].get_text(separator=" ", strip=True)

        var_name = cell(col_var).upper().strip()
        if not var_name or not re.match(r"^[A-Z_][A-Z0-9_]*$", var_name):
            continue  # skip header repeats and blank rows

        start = _parse_int(cell(col_start))
        length = _parse_int(cell(col_length))
        if start is None or length is None:
            continue

        entry: dict = {"var": var_name, "start": start, "length": length}
        label = cell(col_label)
        if label:
            entry["label"] = label
        section = cell(col_section)
        if section:
            entry["section"] = section

        variables.append(entry)

    return variables


def _find_col(headers: list[str], candidates: list[str]) -> int | None:
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h:
                return i
    return None


def _positional_fallback(headers: list[str]) -> tuple:
    """
    If headers are not meaningful, guess column positions.
    Typical CDC layout: Name | Label | Section | Start | Length
    """
    n = len(headers)
    if n >= 5:
        return 0, 1, 2, 3, 4
    elif n == 4:
        return 0, 1, None, 2, 3
    elif n == 3:
        return 0, None, None, 1, 2
    else:
        return 0, None, None, 1, None


def parse_year(year: str, manifest: dict, force: bool = False) -> Path | None:
    info = manifest["years"].get(year)
    if not info:
        console.print(f"[yellow]{year} not in manifest[/yellow]")
        return None

    url_path = info.get("layout_html")
    if not url_path:
        console.print(f"[yellow]{year}: no layout_html in manifest[/yellow]")
        return None

    html_path = _layout_html_path(year, url_path)
    if not html_path.exists():
        console.print(f"[yellow]{year}: layout HTML not downloaded yet ({html_path.name})[/yellow]")
        return None

    out_path = LAYOUTS_DIR / f"{year}_layout.json"
    if out_path.exists() and not force:
        console.print(f"  [dim]skip[/dim] {out_path.name} (exists)")
        return out_path

    console.print(f"  Parsing {year} layout…")
    variables = parse_layout_html(html_path)
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(variables, f, indent=2)

    console.print(f"  [green]{year}[/green]: {len(variables)} variables → {out_path.name}")
    return out_path


@click.command()
@click.option("--years", default="", help="Years to parse. Defaults to all in manifest.")
@click.option("--force", is_flag=True, default=False, help="Re-parse even if output exists.")
def main(years: str, force: bool) -> None:
    """Parse BRFSS variable layout HTML files into JSON."""
    manifest = _load_manifest()
    target_years = [y.strip() for y in years.replace(","," ").split()] if years else list(manifest["years"].keys())
    console.print(f"[bold]Parsing layouts for: {', '.join(sorted(target_years, reverse=True))}[/bold]")
    for year in sorted(target_years, reverse=True):
        parse_year(year, manifest, force=force)
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
