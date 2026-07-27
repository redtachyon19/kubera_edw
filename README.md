# Kubera_EDW

[![CI](https://github.com/redtachyon19/kubera_edw/actions/workflows/ci.yml/badge.svg)](https://github.com/redtachyon19/kubera_edw/actions/workflows/ci.yml)

**Global Asset Management — Enterprise Data Warehouse & BI Platform**

An end-to-end data platform built on **real, freely available public data**: SEC XBRL filings,
World Bank and IMF macro indicators, ECB exchange rates, and daily market prices — extracted,
loaded, modelled into a tested dimensional warehouse, and served through a BI layer.

> Kubera Global Asset Management is **fictional**. The companies are real; Kubera's positions in
> them are a simulation for demonstration only — **no investment advice or ownership claim is
> implied.** Full specification: [`docs/project_spec.md`](docs/project_spec.md).

---

## What's actually in it

| | |
|---|---|
| **Coverage** | 38 companies · 13 countries · 11 currencies |
| **Warehouse** | 548k raw SEC facts → 1,284 financial fact rows · 4 conformed dimensions · 4 facts |
| **Tests** | 83 pytest · 89 dbt nodes (schema, relationship, unit, custom reconciliation) |
| **Orchestration** | 35 Dagster assets, every dbt model first-class, 06:00 daily schedule |
| **Targets** | DuckDB (local) and Neon Postgres — same models, one flag |

## Run it

```bash
git clone https://github.com/redtachyon19/kubera_edw && cd kubera_edw
make setup      # installs uv + Python 3.12, venv, deps — no admin password
make demo       # builds the warehouse from committed fixtures: no API keys, no network
make dashboard  # http://localhost:8501
```

`make demo` is the **minutes path** — it builds the entire DAG from committed CI fixtures, so a
reviewer sees a working warehouse without signing up for anything. To run against live sources,
add the two free keys to `.env` (see [`.env.example`](.env.example)) and use `make pipeline`.

`make help` lists everything.

## Dashboards

Generated from the live warehouse by [`scripts/generate_screenshots.py`](scripts/generate_screenshots.py) —
re-rendered on demand rather than screenshotted, so they cannot drift from the data.

| Portfolio allocation | Fundamentals |
|---|---|
| ![Allocation](docs/screenshots/01_portfolio_allocation.png) | ![Fundamentals](docs/screenshots/02_fundamentals.png) |

| FX impact | Macro overlay |
|---|---|
| ![FX](docs/screenshots/03_fx_impact.png) | ![Macro](docs/screenshots/04_macro_overlay.png) |

![Market performance](docs/screenshots/05_market_performance.png)

## Architecture

Full diagrams — pipeline and star schema — in [`docs/architecture.md`](docs/architecture.md).

```
Public APIs → ingestion/ (throttle, retry, cache) → data/raw/ (immutable)
                                                        ↓
                                        load_raw.py  →  raw.*
                                                        ↓
                            dbt:  staging → intermediate → marts
                                                        ↓
                          Dagster orchestrates  ·  Streamlit serves
```

## Data sources

| Source | Provides | Key |
|---|---|---|
| SEC EDGAR | XBRL company facts (10-K/10-Q, 20-F) | No — User-Agent only |
| World Bank | Country macro indicators | No |
| IMF DataMapper | Independent macro cross-check | No |
| Frankfurter | Daily FX rates, USD base | No |
| Alpha Vantage | Daily prices + the gold benchmark | Free key |

## Three things this project actually had to solve

These are the problems real filing data creates, and the reason the modelling is not trivial:

1. **Nothing about a company can be inferred from its domicile.** 12 of 38 companies file with
   the SEC in a currency other than their home one (Unilever, a UK company, reports in EUR).
   10 carry **both** us-gaap and ifrs-full taxonomies, and Toyota *migrated* between them
   mid-history. Every such attribute is read from the filings by
   [`scripts/verify_universe.py`](scripts/verify_universe.py), never assumed.

2. **SEC's `fy` field describes the filing, not the period.** A FY2025 10-K restates FY2023 and
   FY2024 comparatives, all tagged `fy=2025`. Grain is therefore derived from each fact's own
   period end and measured duration; year-to-date partials are excluded so quarters don't
   double-count, and restatements are de-duplicated to the latest filing.

3. **Currency normalization is where silent corruption lives.** Rates are quoted as foreign
   units per USD, so converting *divides*; inverting it is invisible and catastrophic. It is
   locked down by dbt unit tests, and a `type_money()` macro exists because the default float
   type was 32-bit and was inventing ¥1.2M on Toyota's revenue.

## Known limitations

Documented honestly and in detail in **[`notes_for_red.md`](notes_for_red.md)** — 45 tracked
items with severity. The ones that most affect what you can read from the dashboards:

- **No position weights.** The warehouse holds no share counts or cost basis, so allocation is
  equal-weighted (labelled as such) and portfolio-level return cannot be computed.
- **~100 trading days of price history.** Alpha Vantage's free tier moved full history behind
  its premium plan, so volatility and drawdown cover a short window.
- **Gold is a proxy.** FRED retired its spot USD/oz series entirely; the benchmark is now the
  GLD ETF, priced per share (~1/10 oz), and named `gold_price_usd` rather than `_per_oz`.
- **EBITDA is null for 43% of annual rows** — those filers don't tag a D&A concept.

## Layout

| Path | Purpose |
|---|---|
| `ingestion/` | Source clients, the raw loader, config — `config/companies.yml` is the universe |
| `dbt/` | `staging → intermediate → marts`, snapshots, seeds, and every dbt test |
| `orchestration/` | Dagster asset graph and schedule |
| `dashboards/` | Streamlit BI app |
| `scripts/` | Bootstrap, pipeline, universe verification, screenshot rendering |
| `tests/` | pytest suite (hermetic — no warehouse or network required) |
| `docs/` | Specification, architecture, rendered dashboards |

## Scope

Public disclosed data only. This is deliberately **not** a simulation of private buyout-PE data
(internal transactions, management accounts) — that would require inventing data, which would
undermine the point. Mixed quarterly/annual filing cadence, macro revisions, and non-uniform XBRL
tagging are modelled as the realities they are, not corrected away.

## License

[MIT](LICENSE).
