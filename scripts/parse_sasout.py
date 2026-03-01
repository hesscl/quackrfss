"""
Parse CDC BRFSS SAS DATA step 'sasout' files into structured JSON value labels.

The sasout files (e.g. sasout95.sas, SASOUT97.sas) are SAS DATA step programs
that read the fixed-width ASCII dataset.  Value labels are documented in comment
blocks immediately following each LABEL statement.  Three formats exist:

  1995–1997 — quoted description, /* */ block comment (same or next line):
    LABEL GENHLTH = 'GENERAL HEALTH';
     /*          1 = 'EXCELLENT'
                 2 = 'VERY GOOD'
                 9 = 'REFUSED' */;

  1990–1993 — unquoted description, /* */ block comment:
    LABEL GENHLTH = GENERAL HEALTH
     /*          1 = 'EXCELLENT'
                 9 = 'REFUSED' */;

  1994 — quoted description, * ... *; star comment block:
    LABEL GENHLTH = 'GENERAL HEALTH';
    *********************
    * 1 = 'EXCELLENT'   *
    * 9 = 'REFUSED'     *
    *********************;

We extract these and produce:
  metadata/labels/{year}_labels.json
  {
    "GENHLTH": {"1": "EXCELLENT", "2": "VERY GOOD", ..., "9": "REFUSED"},
    ...
  }

Used for years 1990–1999 that have no PROC FORMAT file.  If a labels JSON
already exists for the year (e.g. 1998, which has Format98.sas), this script
skips it unless --force is given.

Usage:
    python -m scripts.parse_sasout              # all years with sasout_sas key
    python -m scripts.parse_sasout --years 1995 1996
"""

import json
import re
from pathlib import Path

import click
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
RAW_DIR = REPO_ROOT / "data" / "raw"
LABELS_DIR = REPO_ROOT / "metadata" / "labels"

console = Console()

# Pattern A: LABEL VARNAME = [quoted or unquoted desc]; /* ... */
# Handles 1990–1993 (unquoted) and 1995–1997 (quoted).
# The /* comment may start on the same line as the semicolon or the next line.
_LABEL_BLOCK_RE = re.compile(
    r"LABEL\s+(\w+)\s*=\s*"
    r"(?:'[^']*'|\"[^\"]*\"|[^\n;/]*)"  # description: quoted or unquoted to EOL
    r"\s*;?\s*/\*(.*?)\*/",              # optional ; then /* comment body */
    re.IGNORECASE | re.DOTALL,
)

# Pattern B: LABEL VARNAME = 'quoted desc'; \n * ... *; (1994 star-comment style)
# In SAS, * comment ; is a comment statement — the whole box is one comment.
_LABEL_STAR_RE = re.compile(
    r"LABEL\s+(\w+)\s*=\s*"
    r"(?:'[^']*'|\"[^\"]*\"|[^\n;/]*)"  # description
    r"\s*;\s*\n"                          # ; + newline
    r"(\s*\*[^;]+;)",                     # * comment block ... ;
    re.IGNORECASE | re.DOTALL,
)

# Matches a value mapping inside any comment body: <digits> = '<label>'
# Leading zeros (e.g. 01, 02) are stripped by int() conversion in parse_sasout.
_VAL_RE = re.compile(
    r"(-?\d+)\s*=\s*(?:'([^']*)'|\"([^\"]*)\")",
)


def _extract_mappings(comment_body: str) -> dict[str, str]:
    """Extract {code: label} from a comment body using _VAL_RE."""
    mappings: dict[str, str] = {}
    for vm in _VAL_RE.finditer(comment_body):
        code = str(int(vm.group(1)))  # strip leading zeros, e.g. '01' → '1'
        label = (vm.group(2) or vm.group(3) or "").strip()
        if label:
            mappings[code] = label
    return mappings


def parse_sasout(sas_text: str) -> dict[str, dict[str, str]]:
    """
    Parse a BRFSS sasout SAS DATA step into {var_name: {code: label}}.

    Handles three comment styles found across years 1990–1997:
      - /* */ block comments (1990–1997)
      - * ... *; star comment blocks (1994)
    Codes are normalised to plain integers (leading zeros stripped) to match
    load.py's _val_key convention (str(int(float_value))).
    """
    labels: dict[str, dict[str, str]] = {}

    for pattern in (_LABEL_BLOCK_RE, _LABEL_STAR_RE):
        for m in pattern.finditer(sas_text):
            varname = m.group(1).upper()
            if varname in labels:
                continue  # first match wins (block comment preferred)
            mappings = _extract_mappings(m.group(2))
            if mappings:
                labels[varname] = mappings

    return labels


def parse_year(year: str, manifest: dict, force: bool = False) -> Path | None:
    info = manifest["years"].get(year)
    if not info:
        console.print(f"[yellow]{year} not in manifest[/yellow]")
        return None

    url_path = info.get("sasout_sas")
    if not url_path:
        return None  # silently skip years that use parse_formats instead

    sasout_path = RAW_DIR / year / Path(url_path).name
    if not sasout_path.exists():
        console.print(f"[yellow]{year}: sasout file not downloaded yet[/yellow]")
        return None

    out_path = LABELS_DIR / f"{year}_labels.json"
    if out_path.exists() and not force:
        console.print(f"  [dim]skip[/dim] {out_path.name} (exists)")
        return out_path

    console.print(f"  Parsing {year} sasout…")
    sas_text = sasout_path.read_text(encoding="latin-1", errors="replace")
    labels = parse_sasout(sas_text)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(labels, f, indent=2, sort_keys=True)

    console.print(f"  [green]{year}[/green]: {len(labels)} variables → {out_path.name}")
    return out_path


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


@click.command()
@click.option("--years", default="", help="Years to parse. Defaults to all in manifest.")
@click.option("--force", is_flag=True, default=False, help="Re-parse even if output exists.")
def main(years: str, force: bool) -> None:
    """Parse BRFSS sasout SAS files into JSON value labels."""
    manifest = _load_manifest()
    all_years = list(manifest["years"].keys())
    target_years = [y.strip() for y in years.replace(",", " ").split()] if years else all_years
    sasout_years = [y for y in target_years if manifest["years"].get(y, {}).get("sasout_sas")]
    if not sasout_years:
        console.print("[yellow]No years with sasout_sas in manifest[/yellow]")
        return
    console.print(f"[bold]Parsing sasout for: {', '.join(sorted(sasout_years, reverse=True))}[/bold]")
    for year in sorted(sasout_years, reverse=True):
        parse_year(year, manifest, force=force)
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
