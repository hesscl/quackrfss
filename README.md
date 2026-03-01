# 🦆 quackrfss

BRFSS survey data → DuckDB. Clone, run one command, start analyzing.

No manual downloads. No SAS. No hours of prep.

```bash
git clone https://github.com/hesscl/quackrfss
cd quackrfss
pip install uv && uv sync
quackrfss                  # builds brfss.duckdb with 1990–2024 data (~10.1M respondents)
```

Or query instantly — no build required:

```python
import duckdb
con = duckdb.connect()
con.sql("SELECT GENHLTH_lbl, COUNT(*) FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_2024.parquet') GROUP BY 1 ORDER BY 2 DESC").show()
```

---

## ✨ What it does

Downloads CDC [Behavioral Risk Factor Surveillance System (BRFSS)](https://www.cdc.gov/brfss/annual_data/annual_data.htm) data, converts it from SAS Transport (XPT) to Parquet, and builds a DuckDB database you can query instantly:

| Object | Type | Description |
|---|---|---|
| `brfss` | VIEW | All years unified. NULL where a variable was absent in a given year. |
| `brfss_2024` … `brfss_1990` | VIEW | Per-year views backed directly by Parquet files. |
| `variable_labels` | TABLE | `(var, year, label, section)` — human name for each variable. |
| `value_labels` | TABLE | `(var, year, value, label)` — what each numeric code means. |

Every categorical variable gets a `*_lbl` companion column baked into the Parquet (e.g. `GENHLTH_lbl = 'Good'` alongside `GENHLTH = 2`). The `.duckdb` file is tiny (< 10 MB) — it stores only views and metadata; the Parquet files are the source of truth.

---

## 🚀 Quickstart

### Query without building

All 35 years of Parquet files are published at [hesscl/quackrfss](https://huggingface.co/datasets/hesscl/quackrfss) on Hugging Face. Query any year directly with DuckDB — no clone, no build, no 2.5 GB download:

```python
import duckdb
con = duckdb.connect()

# Single year
con.sql("SELECT * FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_2024.parquet') LIMIT 5").show()

# All years at once
con.sql("SELECT YEAR, COUNT(*) FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_*.parquet') GROUP BY 1 ORDER BY 1").show()
```

### Build locally

```bash
# Install dependencies (Python 3.11+)
pip install uv
uv sync

# Full build: all years, all stages
quackrfss

# Just one year to try it out
quackrfss --years 2024

# Specific years, already have raw files
quackrfss --years 2022 2023 --skip-download

# Re-run from scratch
quackrfss --force
```

Then query:

```python
import duckdb
con = duckdb.connect("brfss.duckdb")

# Poor/fair health by state and year
con.sql("""
    SELECT
        _STATE_lbl AS state,
        YEAR,
        ROUND(100.0 * COUNT(*) FILTER (WHERE GENHLTH_lbl IN ('Fair', 'Poor'))
              / COUNT(*), 1) AS pct_fair_poor
    FROM brfss
    WHERE GENHLTH_lbl IS NOT NULL
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

---

## 🔧 Pipeline stages

```
download  →  parse_layout + parse_formats + parse_sasout  →  load  →  schema
 (XPT ZIP)    (HTML layouts, SAS formats, sasout files)      (Parquet)   (DuckDB)
```

Each stage is idempotent — re-running skips work that's already done unless `--force` is passed.

```bash
# Individual stages
python -m scripts.download       --years 2024
python -m scripts.parse_layout   --years 2024    # writes metadata/layouts/
python -m scripts.parse_formats  --years 2024    # writes metadata/labels/ (2000+)
python -m scripts.parse_sasout   --years 1995    # writes metadata/labels/ (1990–1999)
python -m scripts.load           --years 2024    # writes data/parquet/
python -m scripts.schema                         # (re)builds brfss.duckdb
```

---

## 🔍 Metadata lookup

```sql
-- What does a variable name mean?
SELECT * FROM variable_labels WHERE var = 'MENTHLTH';

-- What do the numeric codes mean?
SELECT * FROM value_labels WHERE var = 'GENHLTH' AND year = 2024 ORDER BY value::INT;

-- Find variables related to diabetes across all years
SELECT DISTINCT var, label FROM variable_labels WHERE lower(label) LIKE '%diabet%';
```

---

## ⚖️ Survey weights

BRFSS uses complex sampling. For population-level estimates use the appropriate weight for your year range:

- **2011–2024**: `_LLCPWT` (dual-frame landline + cellphone)
- **1990–2010**: `_FINALWT` (landline only)

```python
df = con.execute("""
    SELECT _STATE_lbl AS state, GENHLTH, _LLCPWT AS weight
    FROM brfss_2024
    WHERE GENHLTH < 7
""").df()
# Then use a survey-weighted analysis package (e.g. samplics, weightedstats)
```

Cross-era comparisons (pre- vs post-2011) require care due to the sampling frame change.

---

## 💾 Storage

| Artifact | Approx. size |
|---|---|
| Raw XPT ZIPs (35 years) | ~2.5 GB |
| Parquet files (35 years) | ~850 MB |
| `brfss.duckdb` | < 10 MB (views + metadata only) |

`data/` and `brfss.duckdb` are gitignored — everyone builds from source. Alternatively, the Parquet files are hosted publicly on [Hugging Face](https://huggingface.co/datasets/hesscl/quackrfss) and can be queried directly without any local build.

---

## 📝 Notes on specific years

- **2020**: COVID-19 forced telephone-only collection and a lower response rate. The `brfss_2020` view is included; treat cross-year comparisons carefully.
- **2011**: No variable layout HTML is available from CDC (PDF only). Variable labels are sourced from XPT metadata instead; value labels are unaffected.
- **2000–2005**: No variable layout HTML available (PDF only). Variable labels come from XPT metadata; value labels from the `.sas` format file.
- **2006–2010**: Layout HTML exists but has only 3 columns (start position, variable name, field length) — no variable label or section. Labels come from XPT metadata.
- **1998**: Has a standard PROC FORMAT `.sas` file — value labels are fully parsed.
- **1990–1997**: Value labels come from SAS DATA step `sasout` files. Three comment styles are handled: `/* */` blocks (1990–1993, 1995–1997), and `* ... *;` star-comment boxes (1994).
- **1999**: The `SASOUT99.sas` file uses a single multi-variable `LABEL` block with no per-variable value comments. Data loads correctly but without `*_lbl` columns.
- **Variable drift**: Variables are added and dropped year to year. The unified `brfss` view fills gaps with NULL. Use `variable_labels` to check which years a given variable appears in.
- **Format files**: 2023–2024 ship `.zip` format archives; 2000–2022 ship raw `.sas` format files; 1990–1999 use `sasout` DATA step programs. All are handled transparently.
- **Dual-frame sampling**: 2011 introduced combined landline + cellphone sampling and the `_LLCPWT` weight. Years 2011–2024 are broadly comparable. Pre-2011 data uses landline-only sampling — cross-era comparisons require care.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| [duckdb](https://duckdb.org/) | Analytical database |
| [pyreadstat](https://github.com/Roche/pyreadstat) | XPT file reading |
| [pyarrow](https://arrow.apache.org/docs/python/) | Parquet writing |
| [httpx](https://www.python-httpx.org/) | HTTP downloads |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | HTML layout parsing |
| [rich](https://github.com/Textualize/rich) | Progress display |
| [click](https://click.palletsprojects.com/) | CLI |

Dev extras (for notebooks): `uv sync --extra dev`

---

## 🗺️ Roadmap

### Phase 1 — 2011–2024 ✅ Done

Covers the dual-frame (landline + cellphone) era with `_LLCPWT` weighting.

### Phase 2 — 2000–2010 ✅ Done

Landline-only era with `_FINALWT` weighting. All 11 years in the manifest.

### Phase 3 — 1990–1999 ✅ Done

Early BRFSS with `_FINALWT` weighting and smaller variable sets. Value labels parsed
from SAS DATA step `sasout` files via regex extraction of embedded comment blocks.
1998 has a proper PROC FORMAT file and is fully labelled.

### Other improvements

- [ ] **Weighted analysis helpers** — thin wrappers that apply `_LLCPWT` by default for common aggregations
- [ ] **Optional materialization** — `--materialize` flag to copy views into real DuckDB tables for environments where Parquet paths change
- [ ] **GitHub Actions CI** — test the pipeline against a single year on each push
- [ ] **Validation checks** — compare loaded row counts against expected counts in `years.json`
- [ ] **Example notebooks** — Jupyter notebooks for common analyses (prevalence trends, state maps, weighted estimates)
- [x] **Published artifact** — Parquet files hosted at [hesscl/quackrfss](https://huggingface.co/datasets/hesscl/quackrfss) on Hugging Face; query any year without building

---

## 📄 License

Pipeline code: [MIT](LICENSE). BRFSS data is public domain (CDC / US Government).
