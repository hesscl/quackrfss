"""
Download BRFSS raw data files from CDC for the years defined in metadata/years.json.

Downloads per year:
  - XPT ZIP  (SAS Transport data file)
  - FORMAT ZIP (SAS format/value-label definitions)
  - Variable layout HTML page
  - Codebook ZIP (documentation only, not parsed)

Files land in data/raw/{year}/.  Already-downloaded files are skipped.

Usage:
    python -m scripts.download              # all years
    python -m scripts.download --years 2023 2024
    python -m scripts.download --years 2020 --skip-codebook
"""

import json
import sys
from pathlib import Path
from typing import Iterable

import click
import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
RAW_DIR = REPO_ROOT / "data" / "raw"

console = Console()


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


def _dest_path(year: str, url_path: str) -> Path:
    filename = Path(url_path).name
    return RAW_DIR / year / filename


def _download_file(
    client: httpx.Client,
    base_url: str,
    url_path: str,
    dest: Path,
    progress: Progress,
    task_id: TaskID,
) -> None:
    url = base_url + url_path
    with client.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        progress.update(task_id, total=total or None)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with tmp.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    progress.advance(task_id, len(chunk))
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise


def download_years(
    years: Iterable[str],
    skip_codebook: bool = False,
    force: bool = False,
) -> None:
    manifest = _load_manifest()
    base_url = manifest["base_url"]
    year_data = manifest["years"]

    # format_zip (2023-2024), format_sas (2000-2022), sasout_sas (1990-1999) are
    # alternate keys for value-label sources depending on the year
    keys = ["xpt_zip", "format_zip", "format_sas", "sasout_sas", "layout_html"]
    if not skip_codebook:
        keys.append("codebook_zip")

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        with httpx.Client(timeout=120, headers={"User-Agent": "quackrfss/0.1"}) as client:
            for year in sorted(years, reverse=True):
                if year not in year_data:
                    console.print(f"[yellow]Warning: {year} not in manifest, skipping.[/yellow]")
                    continue

                info = year_data[year]
                if "notes" in info:
                    console.print(f"[yellow]Note ({year}): {info['notes']}[/yellow]")

                for key in keys:
                    url_path = info.get(key)
                    if not url_path:
                        continue
                    dest = _dest_path(year, url_path)
                    if dest.exists() and not force:
                        console.print(f"  [dim]skip[/dim] {dest.name} (exists)")
                        continue

                    label = f"{year} {key.replace('_', ' ')}"
                    task_id = progress.add_task(label, total=None)
                    try:
                        _download_file(client, base_url, url_path, dest, progress, task_id)
                        progress.update(task_id, description=f"[green]{label}[/green]")
                    except httpx.HTTPStatusError as e:
                        progress.update(task_id, description=f"[red]{label} — HTTP {e.response.status_code}[/red]")
                        console.print(f"[red]  Failed: {url_path}[/red]")


@click.command()
@click.option(
    "--years",
    default="",
    help="Years to download (e.g. --years 2023 2024). Defaults to all years in manifest.",
)
@click.option("--skip-codebook", is_flag=True, default=False, help="Skip codebook ZIPs (docs only, large).")
@click.option("--force", is_flag=True, default=False, help="Re-download even if file already exists.")
def main(years: str, skip_codebook: bool, force: bool) -> None:
    """Download BRFSS raw files from CDC."""
    manifest = _load_manifest()
    target_years = [y.strip() for y in years.replace(","," ").split()] if years else list(manifest["years"].keys())
    console.print(f"[bold]Downloading {len(target_years)} year(s): {', '.join(sorted(target_years, reverse=True))}[/bold]")
    download_years(target_years, skip_codebook=skip_codebook, force=force)
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
