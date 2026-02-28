# 🦆 quackrfss

BRFSS survey data → DuckDB. Clone, run one command, start analyzing.

No manual downloads. No SAS. No hours of prep.

```bash
git clone https://github.com/hesscl/quackrfss
cd quackrfss
pip install uv && uv sync
quackrfss                  # builds brfss.duckdb with 2017–2024 data (~3.5M respondents)
```

---

## ✨ What it does

Downloads CDC [Behavioral Risk Factor Surveillance System (BRFSS)](https://www.cdc.gov/brfss/annual_data/annual_data.htm) data, converts it from SAS Transport (XPT) to Parquet, and builds a DuckDB database you can query instantly:

| Object | Type | Description |
|---|---|---|
| `brfss` | VIEW | All years unified. NULL where a variable was absent in a given year. |
| `brfss_2024` … `brfss_2017` | VIEW | Per-year views backed directly by Parquet files. |
| `variable_labels` | TABLE | `(var, year, label, section)` — human name for each variable. |
| `value_labels` | TABLE | `(var, year, value, label)` — what each numeric code means. |

Every categorical variable gets a `*_lbl` companion column baked into the Parquet (e.g. `GENHLTH_lbl = 'Good'` alongside `GENHLTH = 2`). The `.duckdb` file is tiny (< 5 MB) — it stores only views and metadata; the Parquet files are the source of truth.

---

## 🚀 Quickstart

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
download  →  parse_layout + parse_formats  →  load  →  schema
 (XPT ZIP)    (HTML layouts, SAS formats)    (Parquet)   (DuckDB)
```

Each stage is idempotent — re-running skips work that's already done unless `--force` is passed.

```bash
# Individual stages
python -m scripts.download       --years 2024
python -m scripts.parse_layout   --years 2024   # writes metadata/layouts/
python -m scripts.parse_formats  --years 2024   # writes metadata/labels/
python -m scripts.load           --years 2024   # writes data/parquet/
python -m scripts.schema                        # (re)builds brfss.duckdb
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

BRFSS uses complex sampling. For population-level estimates always use `_LLCPWT`:

```python
df = con.execute("""
    SELECT _STATE_lbl AS state, GENHLTH, _LLCPWT AS weight
    FROM brfss_2024
    WHERE GENHLTH < 7
""").df()
# Then use a survey-weighted analysis package (e.g. samplics, weightedstats)
```

---

## 💾 Storage

| Artifact | Approx. size |
|---|---|
| Raw XPT ZIPs (8 years) | ~500 MB |
| Parquet files (8 years) | ~200 MB |
| `brfss.duckdb` | < 5 MB (views + metadata only) |

`data/` and `brfss.duckdb` are gitignored — everyone builds from source.

---

## 📝 Notes on specific years

- **2020**: COVID-19 forced telephone-only collection and a lower response rate. The `brfss_2020` view is included; treat cross-year comparisons carefully.
- **Variable drift**: Variables are added and dropped year to year. The unified `brfss` view fills gaps with NULL. Use `variable_labels` to check which years a given variable appears in.
- **Format files**: 2023–2024 ship `.zip` format archives; 2017–2022 ship raw `.sas` format files. The parser handles both transparently.

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

### Phase 1 — 2011–2016 (next up)

BRFSS introduced landline + cellphone dual-frame sampling in 2011, making these years broadly comparable to 2017–2024. The file structure is similar but untested:

- [ ] Add `years.json` entries for 2011–2016 with verified CDC URLs
- [ ] Audit `parse_layout` against the older one-column HTML format (likely identical)
- [ ] Audit `parse_formats` against older `.sas` format files
- [ ] Verify XPT column naming consistency with post-2017 data
- [ ] Update `_quackrfss_meta` notes for any methodological differences

### Phase 2 — 2000–2010 (pre-cellphone era)

Before 2011, BRFSS was landline-only and used a different weighting methodology (`_FINALWT` instead of `_LLCPWT`). Cross-era comparisons require care:

- [ ] Map pre-2011 CDC URL patterns into `years.json`
- [ ] Handle `_FINALWT` vs `_LLCPWT` weighting differences in documentation
- [ ] Add year-level notes to `_quackrfss_meta` flagging the methodology break
- [ ] Test HTML layout parser against 2000s-era layout pages (may need a second parser path)

### Phase 3 — 1984–1999 (early BRFSS)

The early years used SAS data step files rather than XPT and have very different variable sets. This phase requires the most new engineering:

- [ ] Investigate whether pre-2000 data is available as XPT or requires a different ingest path
- [ ] Handle significantly smaller variable sets (< 50 core variables for earliest years)
- [ ] Document the scope of cross-decade comparability in the README

### Other improvements

- [ ] **Weighted analysis helpers** — thin wrappers that apply `_LLCPWT` by default for common aggregations
- [ ] **Optional materialization** — `--materialize` flag to copy views into real DuckDB tables for environments where Parquet paths change
- [ ] **GitHub Actions CI** — test the pipeline against a single year on each push
- [ ] **Validation checks** — compare loaded row counts against expected counts in `years.json`
- [ ] **Example notebooks** — Jupyter notebooks for common analyses (prevalence trends, state maps, weighted estimates)
- [ ] **Published artifact** — push a pre-built `brfss.duckdb` to a release or HuggingFace dataset so users can skip the build entirely

---

## 📄 License

Pipeline code: MIT. BRFSS data is public domain (CDC / US Government).
