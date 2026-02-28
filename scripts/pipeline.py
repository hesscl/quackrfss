"""
quackrfss — end-to-end pipeline.

Runs all stages in order:
  1. download   — fetch XPT + FORMAT + layout HTML from CDC
  2. parse      — parse layout HTML and FORMAT SAS files into JSON
  3. load       — XPT → Parquet (with _lbl columns)
  4. schema     — build DuckDB views + metadata tables

Usage:
    quackrfss                           # all years, default DB path
    quackrfss --years 2023 2024
    quackrfss --years 2022 --force
    quackrfss --skip-download           # if files already downloaded
    quackrfss --db /path/to/my.duckdb

Individual stages can also be run directly:
    python -m scripts.download --years 2024
    python -m scripts.parse_layout
    python -m scripts.parse_formats
    python -m scripts.load --years 2024
    python -m scripts.schema
"""

from pathlib import Path

import click
from rich.console import Console
from rich.rule import Rule

from scripts import download, parse_formats, parse_layout, load, schema

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "brfss.duckdb"

console = Console()


def _load_manifest() -> dict:
    import json
    with (REPO_ROOT / "metadata" / "years.json").open() as f:
        return json.load(f)


@click.command()
@click.option(
    "--years",
    default="",
    help="Years to process (e.g. --years 2023 2024). Defaults to 2017-2024.",
)
@click.option("--force", is_flag=True, default=False, help="Re-run all stages even if outputs exist.")
@click.option("--skip-download", is_flag=True, default=False, help="Skip download stage (files already present).")
@click.option("--skip-codebook", is_flag=True, default=False, help="Skip codebook ZIPs during download.")
@click.option("--db", "db_path", default=str(DEFAULT_DB), help="Output DuckDB path.")
def main(
    years: tuple[str, ...],
    force: bool,
    skip_download: bool,
    skip_codebook: bool,
    db_path: str,
) -> None:
    """
    Build the BRFSS DuckDB database from scratch.

    Downloads CDC data, parses metadata, converts to Parquet, and creates
    a DuckDB database with per-year views, a unified `brfss` view, and
    variable/value label lookup tables.
    """
    manifest = _load_manifest()
    target_years = [y.strip() for y in years.replace(","," ").split()] if years else list(manifest["years"].keys())
    target_years_sorted = sorted(target_years, reverse=True)

    console.print(Rule("[bold cyan]quackrfss[/bold cyan]"))
    console.print(f"Years: {', '.join(target_years_sorted)}")
    console.print(f"DB:    {db_path}\n")

    # Stage 1: Download
    if not skip_download:
        console.print(Rule("Stage 1 — Download"))
        download.download_years(target_years_sorted, skip_codebook=skip_codebook, force=force)

    # Stage 2a: Parse layouts
    console.print(Rule("Stage 2a — Parse Layouts"))
    for year in target_years_sorted:
        parse_layout.parse_year(year, manifest, force=force)

    # Stage 2b: Parse value labels
    console.print(Rule("Stage 2b — Parse Formats"))
    for year in target_years_sorted:
        parse_formats.parse_year(year, manifest, force=force)

    # Stage 3: Load to Parquet
    console.print(Rule("Stage 3 — Load to Parquet"))
    for year in target_years_sorted:
        load.load_year(year, manifest, force=force)

    # Stage 4: Build DuckDB
    console.print(Rule("Stage 4 — Build DuckDB"))
    schema.build_database(Path(db_path), force=force)

    console.print(Rule("[bold green]All done[/bold green]"))


if __name__ == "__main__":
    main()
