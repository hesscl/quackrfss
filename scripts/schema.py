"""
Build the DuckDB database from the per-year Parquet files.

Creates:
  - Per-year views:     brfss_2024, brfss_2023, ..., brfss_2017
  - Unified view:       brfss          (all years, NULL for absent variables)
  - Metadata table:     variable_labels  (var, year, label, section)
  - Metadata table:     value_labels     (var, year, value, label)

The Parquet files are the source of truth; DuckDB reads them directly
via scan_parquet / read_parquet.  The .duckdb file stores views +
metadata tables only, so it's small and fast to rebuild.

Usage:
    python -m scripts.schema            # build / refresh database
    python -m scripts.schema --db path/to/custom.duckdb
"""

import json
from pathlib import Path

import click
import duckdb
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
PARQUET_DIR = REPO_ROOT / "data" / "parquet"
LAYOUTS_DIR = REPO_ROOT / "metadata" / "layouts"
LABELS_DIR = REPO_ROOT / "metadata" / "labels"
DEFAULT_DB = REPO_ROOT / "brfss.duckdb"

console = Console()


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


def _available_years(manifest: dict) -> list[str]:
    all_years = list(manifest["years"].keys())
    return [y for y in sorted(all_years, reverse=True) if (PARQUET_DIR / f"BRFSS_{y}.parquet").exists()]


def _load_layout(year: str) -> list[dict]:
    path = LAYOUTS_DIR / f"{year}_layout.json"
    if not path.exists():
        return []
    with path.open() as f:
        return json.load(f)


def _load_labels(year: str) -> dict[str, dict[str, str]]:
    path = LABELS_DIR / f"{year}_labels.json"
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _parquet_columns(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> list[str]:
    # parquet_schema() returns one row per schema node; leaf columns have num_children = 0.
    # The top-level schema root has num_children > 0, so we filter it out.
    rows = con.execute(
        f"SELECT name FROM parquet_schema('{parquet_path}') WHERE num_children IS NULL"
    ).fetchall()
    return [r[0] for r in rows]


def build_database(db_path: Path, force: bool = False) -> None:
    available = _available_years(_load_manifest())
    if not available:
        console.print("[red]No Parquet files found in data/parquet/. Run `load` first.[/red]")
        return

    console.print(f"[bold]Building DuckDB: {db_path}[/bold]")
    console.print(f"  Years: {', '.join(available)}")

    if db_path.exists() and force:
        db_path.unlink()

    con = duckdb.connect(str(db_path))

    # --- Per-year views ---
    year_columns: dict[str, list[str]] = {}
    for year in available:
        pq_path = PARQUET_DIR / f"BRFSS_{year}.parquet"
        cols = _parquet_columns(con, pq_path)
        year_columns[year] = cols
        view_name = f"brfss_{year}"
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{pq_path}')")
        console.print(f"  [green]view[/green] {view_name} ({len(cols)} cols)")

    # --- Unified view across all years ---
    # Collect all column names ever seen (preserving order from latest year)
    all_cols_ordered: list[str] = []
    seen: set[str] = set()
    for year in available:
        for col in year_columns[year]:
            if col not in seen:
                all_cols_ordered.append(col)
                seen.add(col)

    # Build SELECT clause for each year, filling NULL for absent columns
    union_parts = []
    for year in available:
        pq_path = PARQUET_DIR / f"BRFSS_{year}.parquet"
        yr_cols = set(year_columns[year])
        select_exprs = []
        for col in all_cols_ordered:
            if col in yr_cols:
                select_exprs.append(f'"{col}"')
            else:
                select_exprs.append(f"NULL AS \"{col}\"")
        union_parts.append(
            f"SELECT {', '.join(select_exprs)} FROM read_parquet('{pq_path}')"
        )

    unified_sql = "\nUNION ALL\n".join(union_parts)
    con.execute(f"CREATE OR REPLACE VIEW brfss AS\n{unified_sql}")
    total_records = sum(_load_manifest()["years"][y].get("records", 0) for y in available)
    console.print(f"  [green]view[/green] brfss (unified, ~{total_records:,} rows, {len(all_cols_ordered)} cols)")

    # --- variable_labels table ---
    con.execute("""
        CREATE OR REPLACE TABLE variable_labels (
            var     VARCHAR NOT NULL,
            year    SMALLINT NOT NULL,
            label   VARCHAR,
            section VARCHAR,
            PRIMARY KEY (var, year)
        )
    """)
    vl_rows = []
    for year in available:
        for entry in _load_layout(year):
            vl_rows.append((
                entry["var"],
                int(year),
                entry.get("label"),
                entry.get("section"),
            ))
    if vl_rows:
        con.executemany("INSERT OR REPLACE INTO variable_labels VALUES (?, ?, ?, ?)", vl_rows)
    console.print(f"  [green]table[/green] variable_labels ({len(vl_rows):,} rows)")

    # --- value_labels table ---
    con.execute("""
        CREATE OR REPLACE TABLE value_labels (
            var     VARCHAR NOT NULL,
            year    SMALLINT NOT NULL,
            value   VARCHAR NOT NULL,
            label   VARCHAR,
            PRIMARY KEY (var, year, value)
        )
    """)
    val_rows = []
    for year in available:
        labels = _load_labels(year)
        for var, mapping in labels.items():
            for val, lbl in mapping.items():
                val_rows.append((var, int(year), val, lbl))
    if val_rows:
        con.executemany("INSERT OR REPLACE INTO value_labels VALUES (?, ?, ?, ?)", val_rows)
    console.print(f"  [green]table[/green] value_labels ({len(val_rows):,} rows)")

    # --- Convenience: quick summary of what's in the DB ---
    con.execute("""
        CREATE OR REPLACE TABLE _quackrfss_meta (
            key   VARCHAR PRIMARY KEY,
            value VARCHAR
        )
    """)
    con.executemany("INSERT OR REPLACE INTO _quackrfss_meta VALUES (?, ?)", [
        ("years_loaded", ", ".join(available)),
        ("parquet_dir", str(PARQUET_DIR)),
        ("built_at", "now()"),
    ])

    con.close()
    size_mb = db_path.stat().st_size / 1_048_576
    console.print(f"\n[bold green]Database ready:[/bold green] {db_path} ({size_mb:.1f} MB)")
    console.print(
        "\nConnect with:\n"
        "  Python:  import duckdb; con = duckdb.connect('brfss.duckdb')\n"
        "  CLI:     duckdb brfss.duckdb"
    )


@click.command()
@click.option("--db", "db_path", default=str(DEFAULT_DB), help="Path to DuckDB file.")
@click.option("--force", is_flag=True, default=False, help="Delete and rebuild the database from scratch.")
def main(db_path: str, force: bool) -> None:
    """Build DuckDB views and metadata tables from Parquet files."""
    build_database(Path(db_path), force=force)


if __name__ == "__main__":
    main()
