# quackrfss

BRFSS survey data (2017–2024) → DuckDB. Clone, run one command, start analyzing.

No manual downloads. No SAS. No hours of prep.

---

## What it does

Downloads 8 years of [CDC BRFSS](https://www.cdc.gov/brfss/annual_data/annual_data.htm) data (~3.5 million respondents), converts to Parquet, and builds a DuckDB database with:

- **`brfss`** — unified view across all years (~400 columns, NULL where a variable didn't exist that year)
- **`brfss_2024` … `brfss_2017`** — per-year views
- **`variable_labels`** — what each variable name means (`GENHLTH` → "General Health")
- **`value_labels`** — what each code means (`GENHLTH / 1` → "Excellent")
- **`*_lbl` columns** — every categorical variable has a companion string column (e.g. `GENHLTH_lbl = 'Good'`) alongside the original numeric code

## Quickstart

```bash
git clone https://github.com/yourname/quackrfss
cd quackrfss

# Install dependencies (requires Python 3.11+)
pip install uv
uv sync

# Build the full database (downloads ~500 MB of data, takes ~10 min)
quackrfss

# Or just one year to try it out
quackrfss --years 2024
```

Then open Python or the DuckDB CLI:

```python
import duckdb
con = duckdb.connect("brfss.duckdb")

# What share of adults report poor/fair health, by state and year?
con.sql("""
    SELECT
        _STATE_lbl  AS state,
        YEAR,
        ROUND(100.0 * COUNT(*) FILTER (WHERE GENHLTH_lbl IN ('Fair', 'Poor'))
              / COUNT(*), 1) AS pct_fair_poor
    FROM brfss
    WHERE GENHLTH_lbl NOT NULL
    GROUP BY 1, 2
    ORDER BY 3 DESC
    LIMIT 20
""").show()
```

```bash
# DuckDB CLI
duckdb brfss.duckdb
D SELECT GENHLTH_lbl, COUNT(*) FROM brfss_2024 GROUP BY 1 ORDER BY 2 DESC;
```

## Pipeline stages

You can run the full pipeline or individual stages:

```bash
quackrfss                         # full pipeline, all years
quackrfss --years 2023 2024       # specific years
quackrfss --skip-download         # already have raw files
quackrfss --force                 # re-run everything from scratch

# Individual stages
python -m scripts.download --years 2024
python -m scripts.parse_layout
python -m scripts.parse_formats
python -m scripts.load --years 2024
python -m scripts.schema
```

## Database schema

### Main data

| Object | Type | Description |
|---|---|---|
| `brfss` | VIEW | All years unified. NULL where variable absent in a given year. |
| `brfss_2024` … `brfss_2017` | VIEW | Single-year views backed by Parquet files. |

All data tables include:
- `YEAR` — survey year (added by this pipeline)
- Original numeric columns (e.g. `GENHLTH`)
- `*_lbl` string companions for all categorically-labelled variables (e.g. `GENHLTH_lbl`)

### Metadata

| Table | Description |
|---|---|
| `variable_labels` | `(var, year, label, section)` — human name for each variable |
| `value_labels` | `(var, year, value, label)` — what each numeric code means |

```sql
-- Look up what a variable means
SELECT * FROM variable_labels WHERE var = 'MENTHLTH';

-- Look up what codes mean for a variable
SELECT * FROM value_labels WHERE var = 'GENHLTH' AND year = 2024 ORDER BY value::INT;

-- Find all variables related to diabetes
SELECT DISTINCT var, label FROM variable_labels WHERE lower(label) LIKE '%diabet%';
```

## Notes on specific years

- **2020**: Significant methodology changes due to COVID-19 (telephone-only collection, lower response rates). The `brfss_2020` view is included but treat cross-year comparisons carefully. The `_quackrfss_meta` table records a note.
- **Variable drift**: Some variables are added or removed year to year. The unified `brfss` view fills with NULL; use `variable_labels` to check which years a given variable appears in.

## Storage

After a full build:

| Artifact | Size (approx) |
|---|---|
| Raw XPT ZIPs (8 years) | ~500 MB |
| Parquet files (8 years) | ~200 MB |
| `brfss.duckdb` | < 5 MB (views + metadata only) |

Raw files land in `data/` which is gitignored. Parquet and the DuckDB file are also gitignored — everyone builds from source.

## Survey weights

BRFSS uses complex sampling — always use the `_LLCPWT` weight column for population-level estimates. The numeric weight columns are preserved exactly as published by CDC.

```python
# Weighted prevalence example (Python survey package)
import duckdb, pandas as pd
df = duckdb.connect("brfss.duckdb").execute("""
    SELECT _STATE_lbl AS state, GENHLTH, _LLCPWT AS weight
    FROM brfss_2024
    WHERE GENHLTH < 7
""").df()
```

## Dependencies

- [DuckDB](https://duckdb.org/) — analytical database
- [pyreadstat](https://github.com/Roche/pyreadstat) — XPT file reading
- [PyArrow](https://arrow.apache.org/docs/python/) — Parquet writing
- [httpx](https://www.python-httpx.org/) — HTTP downloads
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) — HTML layout parsing
- [rich](https://github.com/Textualize/rich) — progress display
- [click](https://click.palletsprojects.com/) — CLI

## License

Pipeline code: MIT. BRFSS data is public domain (CDC/US Government).
