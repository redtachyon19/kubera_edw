# Kubera_EDW

**Global Asset Management — Enterprise Data Warehouse & BI Platform**

A self-directed data-engineering portfolio project that simulates the data infrastructure of a
global asset-management firm. It sources **real, freely available public data** — SEC filings,
macroeconomic indicators, market prices, FX rates, and gold prices — and runs it through a
governed ETL pipeline into a dimensionally-modeled warehouse with investment-grade BI on top.

> Kubera Global Asset Management is fictional. The companies are real; Kubera's positions in them
> are a simulation for demonstration only — **no investment advice or factual ownership claim is
> implied.** See [`docs/project_spec.md`](docs/project_spec.md) for the full specification.

---

## What this demonstrates

- **ETL engineering** — extraction from multiple heterogeneous public APIs, cleaning, and loading.
- **Dimensional / EDW modeling** — conformed dimensions (company, country, date, currency), fact
  tables, and SCD Type 2 on `dim_company`.
- **Data-quality thinking** — reconciliation checks, mixed quarterly/annual filing cadence,
  currency normalization to USD.
- **Orchestration & reproducibility** — a scheduled, containerized, tested pipeline.

## Architecture

```
Public APIs ──▶ ingestion/ (Python clients) ──▶ data/raw (landed JSON/CSV)
                                                     │
                                                     ▼
                                            dbt: staging ▶ intermediate ▶ marts
                                                     │
                                        Warehouse (DuckDB dev / Postgres prod)
                                                     │
                                     Dagster orchestration  ·  Metabase / Streamlit BI
```

## Data sources

| Source | Provides | Key |
|---|---|---|
| SEC EDGAR (XBRL Frames) | 10-K/10-Q & 20-F/6-K financial facts | No (User-Agent) |
| World Bank / IMF / OECD | Country macro indicators | No |
| FRED | US macro + LBMA gold price series | Free key |
| Frankfurter / exchangerate.host | FX rates for USD normalization | No / Free key |
| Alpha Vantage / Stooq | Daily prices, returns, volatility | Free / No |

## Quick start

```bash
# One command: installs uv + Python 3.12, builds .venv, installs deps, runs checks.
bash scripts/bootstrap.sh
source .venv/bin/activate

# Fill in your free API keys (only needed once you reach extraction)
$EDITOR .env                  # FRED_API_KEY, ALPHA_VANTAGE_API_KEY

# Extract (lands raw responses under data/raw/)
python -m ingestion.sec_edgar_client

# Model (build the warehouse)
cd dbt && dbt build

# Orchestrate: Dagster UI at localhost:3000 (no Docker needed)
export DAGSTER_HOME=$PWD/dagster_home
dagster dev -f orchestration/dagster_pipeline.py

# Re-check the environment any time
bash scripts/verify.sh
```

See [scripts/README.md](scripts/README.md) for details. Docker (`docker compose up`, Dagster
UI on :3000, Metabase on :3001) is optional and only needed from Phase 6 (orchestration).

## Repository layout

| Path | Purpose |
|---|---|
| `ingestion/` | One Python client per data source; `config/companies.yml` = coverage universe |
| `dbt/` | Warehouse modeling — `staging` → `intermediate` → `marts`, plus dbt-native tests |
| `tests/` | Python unit/integration tests (pytest) for the ingestion code |
| `orchestration/` | Dagster pipeline definition |
| `dashboards/` | Metabase setup / Streamlit app |
| `docs/` | Full project spec + architecture diagram |

## Build roadmap

Phase 0 scope-lock → 1 extraction → 2 staging → 3 conformed dims → 4 facts + FX →
5 data-quality tests → 6 orchestration → 7 BI → 8 scale-out → 9 polish.
Full detail in [`docs/project_spec.md`](docs/project_spec.md) §12.

## Status

🚧 Scaffolding in place. Starting universe: 8 companies / 5 countries
(see `ingestion/config/companies.yml`). Implementation follows the phased roadmap above.
