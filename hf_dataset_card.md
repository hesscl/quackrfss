---
license: other
license_name: us-government-works
license_link: https://www.usa.gov/government-copyright
language:
- en
tags:
- brfss
- health
- survey
- public-health
- epidemiology
- cdc
- united-states
- duckdb
pretty_name: BRFSS 1990–2024
size_categories:
- 10M<n<100M
task_categories:
- tabular-classification
- tabular-regression
---

# BRFSS 1990–2024

Behavioral Risk Factor Surveillance System (BRFSS) survey microdata for all 35 years of publicly available data (1990–2024), converted from CDC SAS Transport (XPT) format to Parquet. ~10.1 million respondents.

**Source pipeline:** [hesscl/quackrfss](https://github.com/hesscl/quackrfss)

---

## Quick start

No account, no download, no build. Just DuckDB:

```python
import duckdb
con = duckdb.connect()

# Single year
con.sql("""
    SELECT GENHLTH_lbl, COUNT(*) AS n
    FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_2024.parquet')
    GROUP BY 1 ORDER BY 2 DESC
""").show()

# Trend across all years
con.sql("""
    SELECT
        YEAR,
        ROUND(100.0 * COUNT(*) FILTER (WHERE GENHLTH_lbl IN ('Fair', 'Poor'))
              / COUNT(*), 1) AS pct_fair_poor
    FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_*.parquet')
    WHERE GENHLTH_lbl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""").show()
```

```python
# Load a year into pandas
df = con.sql("""
    SELECT * FROM read_parquet('hf://datasets/hesscl/quackrfss/data/BRFSS_2024.parquet')
""").df()
```

---

## Dataset structure

### Files

One Parquet file per year: `data/BRFSS_{year}.parquet` (1990–2024).

| Years | Files | Approx. rows | Weight variable |
|-------|-------|-------------|-----------------|
| 2011–2024 | `BRFSS_2011.parquet` … `BRFSS_2024.parquet` | 400k–510k/year | `_LLCPWT` |
| 1990–2010 | `BRFSS_1990.parquet` … `BRFSS_2010.parquet` | 80k–450k/year | `_FINALWT` |

### Columns

Every file includes:

- **`YEAR`** (`int16`) — survey year
- **Raw numeric variables** (`float32`) — original CDC-coded values (e.g. `GENHLTH = 3`)
- **`*_lbl` companion columns** (`dict<int8, string>`) — human-readable label for each categorical variable (e.g. `GENHLTH_lbl = 'Good'`). Dictionary-encoded for compact storage.

Variable sets differ across years (BRFSS adds and drops questions). Columns absent in a given year simply aren't present in that year's file.

### Key variables

| Variable | Description |
|----------|-------------|
| `GENHLTH` / `GENHLTH_lbl` | General health (Excellent → Poor) |
| `_STATE` / `_STATE_lbl` | State FIPS code |
| `_LLCPWT` | Final survey weight (2011–2024) |
| `_FINALWT` | Final survey weight (1990–2010) |
| `SEX` / `SEX_lbl` | Sex of respondent |
| `AGE` / `_AGEG5YR_lbl` | Age / age group |
| `SMOKE100` | Ever smoked 100+ cigarettes |
| `DIABETE3` / `DIABETE4` | Ever told have diabetes |
| `BPHIGH4` | Ever told blood pressure high |

---

## Comparability notes

- **2011 methodology change**: BRFSS introduced combined landline + cellphone sampling in 2011 and a new weighting methodology (`_LLCPWT`). Pre- and post-2011 data are not directly comparable without adjustment.
- **2020**: COVID-19 forced telephone-only collection and reduced response rates.
- **1999**: No value-label columns (`*_lbl`) — the source SAS file for this year contains no parseable value mappings.
- **Variable drift**: Questions are added and dropped year to year. Always check which years a variable appears in before running cross-year analyses.

---

## Source data

BRFSS data is collected annually by state health departments in collaboration with CDC. Raw XPT files are published at:
[https://www.cdc.gov/brfss/annual_data/annual_data.htm](https://www.cdc.gov/brfss/annual_data/annual_data.htm)

This dataset was built using [quackrfss](https://github.com/hesscl/quackrfss), which downloads the XPT files, parses value labels from SAS format and sasout files, and converts to Parquet with `*_lbl` companion columns.

---

## License

BRFSS data is produced by the US Centers for Disease Control and Prevention and is in the public domain as a work of the US federal government. Pipeline code is MIT licensed.

---

## Citation

If you use this dataset, please cite the CDC BRFSS program:

> Centers for Disease Control and Prevention (CDC). Behavioral Risk Factor Surveillance System Survey Data. Atlanta, Georgia: U.S. Department of Health and Human Services, Centers for Disease Control and Prevention, 1990–2024.
