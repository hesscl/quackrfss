"""
Parse CDC BRFSS SAS FORMAT files into structured JSON value labels.

The SAS FORMAT files define how numeric codes map to human-readable labels,
e.g.:  GENHLTH  1="Excellent"  2="Very good"  3="Good" ...

The ZIP contains a .sas file with PROC FORMAT blocks like:

    VALUE GENHLTH
      1 = 'Excellent'
      2 = 'Very good'
      ...
      9 = 'Refused'
    ;

We extract these and produce:
  metadata/labels/{year}_labels.json
  {
    "GENHLTH": {"1": "Excellent", "2": "Very good", ..., "9": "Refused"},
    "_STATE":  {"1": "Alabama", "2": "Alaska", ...},
    ...
  }

Note: SAS format names don't always match variable names exactly.
  - Format names often have a leading underscore for calculated vars (_STATE → $STATE or SSTATE)
  - We normalise by stripping leading $ and trailing F/N suffixes

Usage:
    python -m scripts.parse_formats              # all downloaded years
    python -m scripts.parse_formats --years 2023 2024
"""

import json
import re
import zipfile
from pathlib import Path

import click
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
RAW_DIR = REPO_ROOT / "data" / "raw"
LABELS_DIR = REPO_ROOT / "metadata" / "labels"

console = Console()

# Matches:  VALUE <name>  (with optional $ prefix for character formats)
_FORMAT_BLOCK_RE = re.compile(
    r"VALUE\s+(\$?[\w]+)(.*?)(?=\bVALUE\b|\bRUN\b|\bQUIT\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# Matches a single mapping line:  <range_or_val> = '<label>'
# Values can be numeric, quoted strings, or ranges like 1-5 or 1,2,3
_MAPPING_RE = re.compile(
    r"""
    \s*
    (                           # value / range spec
        -?\d+\s*-\s*-?\d+       # numeric range  1-9 or -2--1
        | -?\d+(?:\s*,\s*-?\d+)+ # list  1,2,3
        | -?\d+                 # single integer
        | '[^']*'               # quoted string value
        | "[^"]*"               # double-quoted
        | OTHER                 # SAS OTHER keyword
    )
    \s*=\s*
    (?:'([^']*)'|"([^"]*)")     # label in single or double quotes
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalise_format_name(raw_name: str) -> str:
    """
    Normalise a SAS format name for storage in the labels JSON.

    Kept intentionally minimal: just strip $ and uppercase.
    The S-prefix → underscore mapping (e.g. SSTATE → _STATE) is NOT done here
    because many legitimate variable names start with S (SEXVAR, SMOK100_, etc.).
    That matching is handled in load.py where actual XPT column names are known.
    """
    name = raw_name.strip().lstrip("$").upper()
    return name


def parse_format_sas(sas_text: str) -> dict[str, dict[str, str]]:
    """
    Parse a SAS PROC FORMAT block into {format_name: {value_str: label}}.
    """
    labels: dict[str, dict[str, str]] = {}

    for m in _FORMAT_BLOCK_RE.finditer(sas_text):
        raw_name = m.group(1)
        block = m.group(2)
        name = _normalise_format_name(raw_name)

        mappings: dict[str, str] = {}
        for mm in _MAPPING_RE.finditer(block):
            val_spec = mm.group(1).strip()
            label = (mm.group(2) or mm.group(3) or "").strip()

            # Expand simple ranges like 88-99 into individual keys,
            # but only for short ranges (≤20 values) to avoid blowup
            range_m = re.match(r"^(-?\d+)\s*-\s*(-?\d+)$", val_spec)
            if range_m:
                lo, hi = int(range_m.group(1)), int(range_m.group(2))
                if 0 < hi - lo <= 20:
                    for v in range(lo, hi + 1):
                        mappings[str(v)] = label
                else:
                    mappings[val_spec] = label  # keep as range string
            elif "," in val_spec and not val_spec.startswith("'"):
                for part in val_spec.split(","):
                    mappings[part.strip()] = label
            else:
                mappings[val_spec.strip("'\"")] = label

        if mappings:
            labels[name] = mappings

    return labels


def _read_sas_text(format_path: Path) -> str:
    """Read SAS FORMAT text from either a ZIP or a raw .sas file."""
    if format_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(format_path) as zf:
            sas_names = [n for n in zf.namelist() if n.lower().endswith(".sas")]
            if not sas_names:
                raise ValueError(f"No .sas file found in {format_path}")
            # Prefer the main FORMAT file (not SASOUT or TRANSPRT)
            main = next(
                (n for n in sas_names if re.search(r"format\d", n, re.IGNORECASE)),
                sas_names[0],
            )
            return zf.read(main).decode("latin-1", errors="replace")
    else:
        return format_path.read_text(encoding="latin-1", errors="replace")


def _find_format_file(year: str, info: dict) -> Path | None:
    """Locate the downloaded FORMAT file (ZIP or raw .sas) for a given year."""
    for key in ("format_zip", "format_sas"):
        url_path = info.get(key)
        if url_path:
            path = RAW_DIR / year / Path(url_path).name
            if path.exists():
                return path
    return None


def parse_year(year: str, manifest: dict, force: bool = False) -> Path | None:
    info = manifest["years"].get(year)
    if not info:
        console.print(f"[yellow]{year} not in manifest[/yellow]")
        return None

    format_path = _find_format_file(year, info)
    if format_path is None:
        console.print(f"[yellow]{year}: FORMAT file not downloaded yet[/yellow]")
        return None

    out_path = LABELS_DIR / f"{year}_labels.json"
    if out_path.exists() and not force:
        console.print(f"  [dim]skip[/dim] {out_path.name} (exists)")
        return out_path

    console.print(f"  Parsing {year} formats…")
    sas_text = _read_sas_text(format_path)
    labels = parse_format_sas(sas_text)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(labels, f, indent=2, sort_keys=True)

    console.print(f"  [green]{year}[/green]: {len(labels)} format blocks → {out_path.name}")
    return out_path


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


@click.command()
@click.option("--years", default="", help="Years to parse. Defaults to all in manifest.")
@click.option("--force", is_flag=True, default=False, help="Re-parse even if output exists.")
def main(years: str, force: bool) -> None:
    """Parse BRFSS SAS FORMAT ZIPs into JSON value labels."""
    manifest = _load_manifest()
    target_years = [y.strip() for y in years.replace(","," ").split()] if years else list(manifest["years"].keys())
    console.print(f"[bold]Parsing formats for: {', '.join(sorted(target_years, reverse=True))}[/bold]")
    for year in sorted(target_years, reverse=True):
        parse_year(year, manifest, force=force)
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
