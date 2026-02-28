"""
Load a BRFSS XPT file into a Parquet file, adding a `year` column and
`*_lbl` companion columns for every categorically-labelled variable.

For each variable that has an entry in the year's labels JSON:
  - Keep the original numeric column (e.g. GENHLTH = 3)
  - Add a string column immediately after it  (e.g. GENHLTH_lbl = "Good")

Columns that have no value labels (continuous measures, weights, IDs) are
left as-is. DuckDB's columnar/dictionary encoding makes the extra string
columns very cheap.

Output: data/parquet/BRFSS_{year}.parquet

Usage:
    python -m scripts.load              # all years with downloaded XPT
    python -m scripts.load --years 2023 2024
    python -m scripts.load --years 2022 --force
"""

import json
import zipfile
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
import pyreadstat
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "metadata" / "years.json"
RAW_DIR = REPO_ROOT / "data" / "raw"
PARQUET_DIR = REPO_ROOT / "data" / "parquet"
LAYOUTS_DIR = REPO_ROOT / "metadata" / "layouts"
LABELS_DIR = REPO_ROOT / "metadata" / "labels"

console = Console()

# Sentinel values that should always map to null in the label column.
# These are standard BRFSS "don't know / refused / missing" codes.
_NULL_CODES = {"7", "77", "777", "7777", "77777", "9", "99", "999", "9999", "99999", "BLANK"}


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        return json.load(f)


def _load_labels(year: str) -> dict[str, dict[str, str]]:
    path = LABELS_DIR / f"{year}_labels.json"
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _load_layout(year: str) -> list[dict]:
    path = LAYOUTS_DIR / f"{year}_layout.json"
    if not path.exists():
        return []
    with path.open() as f:
        return json.load(f)


def _resolve_format_name(col: str, labels: dict) -> str | None:
    """
    Find the format name in the labels dict that corresponds to an XPT column.

    CDC SAS FORMAT files use the variable name directly (e.g. SEXVAR → SEXVAR)
    or, for some calculated variables starting with '_', replace the leading
    underscore with 'S' (e.g. _STATE → SSTATE).  We check both.
    """
    if col in labels:
        return col
    if col.startswith("_"):
        s_name = "S" + col[1:]
        if s_name in labels:
            return s_name
    return None


def _xpt_path(year: str, url_path: str) -> Path:
    """Locate the extracted XPT file, extracting from ZIP if needed."""
    zip_path = RAW_DIR / year / Path(url_path).name
    if not zip_path.exists():
        raise FileNotFoundError(f"XPT ZIP not found: {zip_path}")

    extract_dir = RAW_DIR / year / "xpt"
    extract_dir.mkdir(parents=True, exist_ok=True)

    def _find_xpt(directory: Path) -> Path | None:
        for p in directory.iterdir():
            if p.name.strip().upper().endswith(".XPT"):
                return p
        return None

    # Check if already extracted
    existing = _find_xpt(extract_dir)
    if existing:
        return existing

    console.print(f"  Extracting {zip_path.name}…")
    with zipfile.ZipFile(zip_path) as zf:
        xpt_names = [n for n in zf.namelist() if n.strip().upper().endswith(".XPT")]
        if not xpt_names:
            raise ValueError(f"No .XPT file in {zip_path}")
        zf.extract(xpt_names[0], extract_dir)

    found = _find_xpt(extract_dir)
    if found is None:
        raise ValueError(f"Extraction succeeded but no .XPT found in {extract_dir}")
    return found


def _patch_layout_labels(year: str, xpt_var_labels: dict[str, str]) -> None:
    """
    Back-fill variable labels sourced from XPT metadata into the layout JSON.
    Only writes entries that are missing a label; never overwrites existing ones.
    """
    path = LAYOUTS_DIR / f"{year}_layout.json"
    if not path.exists():
        return
    with path.open() as f:
        layout = json.load(f)

    changed = False
    for entry in layout:
        if "label" not in entry and entry["var"] in xpt_var_labels:
            entry["label"] = xpt_var_labels[entry["var"]]
            changed = True

    if changed:
        with path.open("w") as f:
            json.dump(layout, f, indent=2)


def _build_label_lookup(labels: dict[str, dict[str, str]]) -> dict[str, dict[str, str | None]]:
    """
    Pre-process the labels dict: keys are already strings of the numeric value.
    Sentinel codes map to None so they become NULL in the Parquet column.
    """
    processed = {}
    for var, mapping in labels.items():
        new_mapping: dict[str, str | None] = {}
        for k, v in mapping.items():
            if k.upper() in _NULL_CODES:
                new_mapping[k] = None
            else:
                new_mapping[k] = v
        processed[var] = new_mapping
    return processed


def load_year(year: str, manifest: dict, force: bool = False) -> Path | None:
    info = manifest["years"].get(year)
    if not info:
        console.print(f"[yellow]{year} not in manifest[/yellow]")
        return None

    out_path = PARQUET_DIR / f"BRFSS_{year}.parquet"
    if out_path.exists() and not force:
        console.print(f"  [dim]skip[/dim] BRFSS_{year}.parquet (exists)")
        return out_path

    url_path = info["xpt_zip"]
    try:
        xpt_path = _xpt_path(year, url_path)
    except FileNotFoundError as e:
        console.print(f"[yellow]{year}: {e}[/yellow]")
        return None

    console.print(f"  Reading {xpt_path.name} …")
    # BRFSS XPT files use Latin-1 encoded variable labels (legacy SAS format)
    df, meta = pyreadstat.read_xport(str(xpt_path), encoding="latin1")

    # Normalise column names to uppercase (pyreadstat may preserve case)
    df.columns = [c.upper() for c in df.columns]

    # Add survey year column at front
    df.insert(0, "YEAR", int(year))

    # Capture variable labels from XPT metadata and patch the layout JSON.
    # The XPT binary format carries per-column labels natively; this is more
    # reliable than the HTML layout page which may omit them.
    xpt_var_labels: dict[str, str] = {}
    if hasattr(meta, "column_labels") and meta.column_labels:
        raw_labels = meta.column_labels
        col_names = [c.upper() for c in (meta.column_names or df.columns)]
        xpt_var_labels = {
            col: lbl
            for col, lbl in zip(col_names, raw_labels)
            if lbl and lbl.strip()
        }

    if xpt_var_labels:
        _patch_layout_labels(year, xpt_var_labels)

    raw_labels_dict = _load_labels(year)
    label_lookup = _build_label_lookup(raw_labels_dict)

    # Build an ordered list of columns: for each col that has labels,
    # insert a <COL>_lbl column immediately after it.
    base_cols = list(df.columns)
    new_col_order = []
    label_additions: dict[str, list[str | None]] = {}

    def _val_key(v) -> str:
        """Convert a raw XPT cell value to the string key used in the labels dict."""
        if v is None:
            return "BLANK"
        try:
            f = float(v)
            if f != f:  # NaN
                return "BLANK"
            return str(int(f))
        except (ValueError, TypeError):
            return "BLANK"

    for col in base_cols:
        new_col_order.append(col)
        fmt_name = _resolve_format_name(col, label_lookup)
        if fmt_name is not None:
            lbl_col = col + "_lbl"
            new_col_order.append(lbl_col)
            mapping = label_lookup[fmt_name]
            label_additions[lbl_col] = [mapping.get(_val_key(v)) for v in df[col]]

    # Add label columns to the dataframe
    for lbl_col, values in label_additions.items():
        df[lbl_col] = values

    df = df[new_col_order]

    console.print(
        f"  {year}: {len(df):,} rows × {len(df.columns)} cols "
        f"({len(label_additions)} label columns added)"
    )

    # Convert to PyArrow table for Parquet write.
    #
    # Strategy: let PyArrow infer types from pandas (handles mixed object/numeric
    # columns correctly), then cast numeric columns down to float32 (sufficient
    # for BRFSS codes and saves space), and apply dictionary encoding to _lbl
    # columns for maximum compression of repeated string values.

    lbl_cols = {col for col in df.columns if col.endswith("_lbl")}

    # Build base table via pandas→PyArrow inference (handles IDATE strings, etc.)
    base_df = df[[c for c in df.columns if c not in lbl_cols]]
    table = pa.Table.from_pandas(base_df, preserve_index=False)

    # Downcast float64 → float32 for numeric columns (BRFSS codes never need f64)
    new_schema = []
    new_cols = []
    for i, field in enumerate(table.schema):
        col_arr = table.column(i)
        if pa.types.is_floating(field.type) and field.name != "YEAR":
            col_arr = col_arr.cast(pa.float32())
            new_schema.append(field.with_type(pa.float32()))
        elif field.name == "YEAR":
            col_arr = col_arr.cast(pa.int16())
            new_schema.append(field.with_type(pa.int16()))
        else:
            new_schema.append(field)
        new_cols.append(col_arr)

    # Add dictionary-encoded _lbl columns in original order
    for col in df.columns:
        if col not in lbl_cols:
            continue
        raw = df[col].tolist()
        cleaned = [x if isinstance(x, str) else None for x in raw]
        arr = pa.array(cleaned, type=pa.string()).dictionary_encode()
        new_schema.append(pa.field(col, pa.dictionary(pa.int8(), pa.string())))
        new_cols.append(arr.cast(pa.dictionary(pa.int8(), pa.string())))

    # Reorder columns to match original df column order
    col_index = {f.name: i for i, f in enumerate(new_schema)}
    ordered_indices = [col_index[col] for col in df.columns]
    table = pa.table(
        {new_schema[i].name: new_cols[i] for i in ordered_indices},
        schema=pa.schema([new_schema[i] for i in ordered_indices]),
    )

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        out_path,
        compression="zstd",
        compression_level=3,
        write_statistics=True,
        row_group_size=50000,
    )

    size_mb = out_path.stat().st_size / 1_048_576
    console.print(f"  [green]{year}[/green] → BRFSS_{year}.parquet ({size_mb:.1f} MB)")
    return out_path


@click.command()
@click.option("--years", default="", help="Years to load. Defaults to all in manifest.")
@click.option("--force", is_flag=True, default=False, help="Re-build even if Parquet already exists.")
def main(years: str, force: bool) -> None:
    """Convert BRFSS XPT files to Parquet with label columns."""
    manifest = _load_manifest()
    target_years = [y.strip() for y in years.replace(","," ").split()] if years else list(manifest["years"].keys())
    console.print(f"[bold]Loading {len(target_years)} year(s): {', '.join(sorted(target_years, reverse=True))}[/bold]")
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as _p:
        for year in sorted(target_years, reverse=True):
            load_year(year, manifest, force=force)
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
