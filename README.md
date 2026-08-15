# Kubera_EDW

[![CI](https://github.com/redtachyon19/kubera_edw/actions/workflows/ci.yml/badge.svg)](https://github.com/redtachyon19/kubera_edw/actions/workflows/ci.yml)

An **investment research platform** built on a real enterprise data warehouse: extraction,
loading, transformation, orchestration and BI in a single monorepo. Public filings and open
market data go in one end; a research terminal comes out the other.

Nothing here is owned or simulated. Companies are **indexed into the warehouse** — press
backfill on any SEC registrant and its full XBRL filing history is resolved, landed, modelled
and queryable within minutes. **40 issuers** are indexed today across 13 countries and 11
currencies: US 10-K filers alongside foreign 20-F filers reporting in EUR, JPY, GBP, CNY, KRW,
INR, BRL, CHF, MXN and AUD. That number is not a fixed universe, it is just where the index
has got to.

The questions it answers are the ones a research or quant desk actually asks — as-filed
fundamentals normalised across currencies, valuation multiples that survive a cross-listing,
bilateral trade between any two economies, purchasing power measured against gold rather than
a currency that is itself moving, and the macro backdrop behind any of it.

**Every data source is free and public.** Most need no key at all. Nothing here uses private,
paid or licensed data — the point is a warehouse of genuine analytical depth built entirely on
disclosed filings and open data.

> This is **public disclosed data**, not private operational data. It does not claim to
> replicate what a firm sees internally (invoice-level transactions, private management
> accounts). That is a scope decision, stated plainly rather than left implied.

For the deep technical treatment — physical storage layout, schema-by-schema column detail,
and the mechanics of every transformation — see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Quickstart

No API keys and no network required — the repo ships CI fixtures that build the full warehouse
offline.

```bash
make setup && make demo && make hub
```

| Command | What it does |
|---|---|
| `make setup` | Installs `uv`, Python 3.12, `.venv`, and all dependencies. No admin password. |
| `make demo` | Builds the warehouse from committed fixtures — **no keys, no network** |
| `make hub` | Serves the research terminal at http://localhost:5173 (hub + every dashboard) |
| `make db-up` | Starts the local Postgres warehouse on `localhost:5432` |
| `make db-down` | Stops it. `make db-status` reports size; `make db-psql` opens a shell |
| `make pipeline` | Full live pipeline into local Postgres (needs `.env` keys) |
| `make prod` | Full live pipeline into a hosted Postgres server |
| `make orchestrate` | Serves the Dagster UI at http://localhost:3000 |
| `make test` | Python suite + every dbt test |
| `make lint` | `ruff check` + `ruff format --check` |
| `make verify` | Re-checks environment: python, deps, lint, tests, dbt connection |
| `make universe` | Re-verifies every company against SEC EDGAR |
| `make screenshots` | Re-renders the README charts **and** the Dashboards card thumbnails |
| `make clean` | Removes build artefacts (keeps landed raw data and the venv) |

---

## Repo directory

```
kubera_edw/
├── ingestion/                    # EXTRACT — one client per external source
│   ├── base_client.py            #   shared HTTP: throttle, retry/backoff, freshness cache, landing
│   ├── config_loader.py          #   companies.yml reader, .env loading, API-key placeholder detection
│   ├── sec_edgar_client.py       #   SEC EDGAR XBRL companyfacts
│   ├── world_bank_client.py      #   World Bank country-year macro indicators
│   ├── imf_client.py             #   IMF DataMapper (cross-check on World Bank)
│   ├── fx_client.py              #   Frankfurter daily FX, base USD
│   ├── prices_client.py          #   Daily equity prices (Alpha Vantage / Stooq)
│   ├── gold_price_client.py      #   Gold benchmark (FRED series or GLD proxy)
│   ├── generate_seeds.py         #   companies.yml -> dbt/seeds/seed_companies.csv
│   ├── load_raw.py               #   LOAD — parses data/raw/ into the warehouse raw schema
│   └── config/companies.yml      #   THE COVERAGE UNIVERSE — single source of truth
│
├── dbt/                          # TRANSFORM
│   ├── models/staging/           #   7 views — cast, rename, clean. No business logic.
│   ├── models/intermediate/      #   3 views — the hard logic (concept pivot, FX fill, USD normalize)
│   ├── models/marts/             #   8 tables — 4 conformed dimensions + 4 facts
│   ├── snapshots/                #   company_snapshot — SCD2 history of the universe
│   ├── seeds/                    #   concept map, country/currency reference, company seed
│   ├── seeds/ci_raw/             #   committed fixtures so CI builds with no network
│   ├── macros/                   #   generate_schema_name, type_money (cross-adapter money type)
│   ├── tests/                    #   4 custom data tests beyond schema tests
│   ├── dbt_project.yml           #   layer materializations + schema routing
│   └── profiles.yml              #   dev (Postgres) | ci (DuckDB) | prod (Postgres)
│
├── orchestration/
│   ├── dagster_pipeline.py       # 41 assets, 2 jobs, 1 failure sensor, 06:00 daily schedule
│   └── dagster_home/             #   DAGSTER_HOME — only dagster.yaml is committed;
│                                 #   run history and sensor cursors are runtime state
│
├── dashboard_hub/                # BI — hub & spoke, one front door for every dashboard
│   ├── dashboards.json           # single source of truth — nav, proxy, processes, palette
│   ├── sectors.json              # editorial sector definitions behind the Sectors page
│   ├── companies.json            # the browsable universe — generated, not hand-edited
│   ├── countries.json            # every country + capital coordinates, behind the globe
│   ├── registry.py               # reads dashboards.json (Python side)
│   ├── run_local.py              # starts every dashboard service + the market API
│   ├── market_api.py             # stdlib JSON endpoint behind the hub's native pages
│   ├── lib/                      # shared code
│   │   ├── db.py                 #   read-only warehouse connection, 5-min cache
│   │   ├── queries.py            #   SQL against marts -> pandas
│   │   ├── warehouse.py          #   the same marts without Streamlit, for the market API
│   │   ├── filings.py            #   long-run quarterly figures, read live from SEC EDGAR
│   │   ├── market_data.py        #   live prices/search/financials (Yahoo) — no key
│   │   ├── world.py              #   governments, currencies, gold, energy, news
│   │   ├── trade.py              #   bilateral trade (WITS) + trade composition
│   │   ├── imagery.py            #   company logos and country flags, disk-cached
│   │   ├── theme.py              #   palette + Altair theme, both stocks
│   │   └── ui.py                 #   page chrome, empty states, chart helpers
│   ├── hub/                      # the website — Vite + React + TypeScript
│   └── dashboards/<module>/app.py  # one independent Streamlit dashboard each
│
├── scripts/
│   ├── bootstrap.sh              # uv + Python 3.12 + venv + deps
│   ├── pipeline.sh               # extract -> seeds -> load -> dbt build
│   ├── verify.sh                 # environment health check
│   ├── verify_universe.py        # re-validates every company against SEC EDGAR
│   ├── generate_country_reference.py  # rebuilds dashboard_hub/countries.json
│   ├── generate_land_outline.py  # rebuilds the globe's coastlines (Natural Earth)
│   └── generate_screenshots.py   # renders dashboard charts to docs/screenshots/
│
├── tests/                        # 202 pytest tests (mocked HTTP via respx)
├── docs/                         # screenshots
├── data/                         # kubera_edw.duckdb + data/raw/ landing zone (gitignored)
│
├── Makefile                      # every workflow above
├── Dockerfile                    # orchestrator image
├── docker-compose.yml            # postgres warehouse + dagster orchestrator + metabase
├── requirements.txt
└── .github/workflows/ci.yml      # lint + test, then a full offline dbt build
```

---

## Ingestion

Ingestion is **extract-and-land only**. Each client fetches from a public API and writes the
response to `data/raw/<source>/` essentially as received. No reshaping, no business logic, no
type coercion — that is deliberately deferred so extraction stays re-runnable and the warehouse
can be rebuilt without re-hitting rate-limited APIs.

A separate step, `load_raw.py`, parses those landed files into warehouse tables. So the flow is
genuinely **E → L → T**: extract to files, load to `raw.*`, transform in dbt.

### Sources

| Source | Purpose | Base URL | Key | Lands as |
|---|---|---|---|---|
| **SEC EDGAR** | XBRL company facts — every financial figure | `data.sec.gov` | none¹ | `companyfacts_CIK*.json` |
| **World Bank** | Country-year macro (GDP, inflation, unemployment) for **every country**, plus the country reference | `api.worldbank.org/v2` | none | `<indicator>_<date>.json`, `countries_<date>.json` |
| **IMF DataMapper** | Independent cross-check on World Bank | `imf.org/external/datamapper/api/v1` | none | `<indicator>_<code>.json` |
| **Frankfurter** | Daily FX rates, base USD | `api.frankfurter.dev/v1` | none | `timeseries_USD_*.json` |
| **World Bank WITS** | Bilateral trade — who trades with whom, both directions | `wits.worldbank.org/API/V1` | none | read live by the hub, disk-cached |
| **Google News RSS** | Per-country economy and market headlines | `news.google.com/rss` | none | read live by the hub, cached 30 min |
| **Google favicons / DuckDuckGo** | Company logos, by domain | `google.com/s2/favicons` | none | `data/image_cache/`, 30-day TTL |
| **flagcdn** | Country flags, by ISO2 | `flagcdn.com` | none | `data/image_cache/`, 30-day TTL |
| **IMF PortWatch** | Daily port and chokepoint activity since 2019, plus port→country flows by industry | `services9.arcgis.com/…` | none | `portwatch/**/*.parquet` |
| **US Census** | US trade by port of entry × partner × HS chapter, monthly | `api.census.gov/data/timeseries/intltrade` | `CENSUS_API_KEY`² | `census_trade/**/*.parquet` |
| **Alpha Vantage** | Daily equity prices + gold proxy | `alphavantage.co` | `ALPHA_VANTAGE_API_KEY` | `av_<TICKER>.json` |
| **FRED** | Gold benchmark (see note) | `api.stlouisfed.org/fred` | `FRED_API_KEY` | `gold_lbma_fixing.json` |

¹ SEC requires no key but **does** require a descriptive `SEC_EDGAR_USER_AGENT` identifying the
requester, in the form `"Name email@example.com"`. Requests without it are rejected.

² Census's published free tier ("500 requests per IP per day, no key") is **out of date**. As of
August 2026 every data endpoint under `api.census.gov` 302-redirects to `missing_key.html`
without one; only the `variables.json` metadata is still open. The key is free and instant. With
it absent, `census_trade_client` logs and returns, and the dbt models that read it disable
themselves via `enabled: env_var('CENSUS_API_KEY', '') != ''` — the global PortWatch layer does
not depend on it.

**PortWatch note.** Every table is named "Daily" and the service refreshes **weekly**, Tuesdays
around 09:00 ET, with an observed lag of about five days — so it is a trend instrument, not a
live feed, and the desk prints the date its numbers stop at rather than implying otherwise. Two
traps are worth knowing: its `date` field is typed `DateOnly` but returns a `"YYYY-MM-DD"` string
where every other ArcGIS date is epoch milliseconds, while its *disruption* dates really are
epoch milliseconds; and its `export`/`import` fields are named from the **partner country's**
point of view, so a port's `import` row is cargo *leaving* that port. Staging translates the
latter into port-relative `inbound`/`outbound` — see `stg_portwatch__trade_ribbons.sql`, which
shows the arithmetic that proves it. Licence: attribution required, bulk redistribution **not**
granted, which is why the figures are served from our own warehouse rather than proxied.

**Gold note.** The original source, FRED series `GOLDAMGBD228NLBM` (LBMA daily fixing), no longer
exists — FRED returns `400 The series does not exist`. The default backend is now the **GLD ETF**
(SPDR Gold Shares, ~1/10 troy oz per share) via Alpha Vantage, which reuses the price key. The
FRED code path is retained and works if you pass an explicit `series_id`. Whichever backend runs,
the landed payload keeps FRED's `{"observations": [{date, value}]}` shape, so downstream staging
does not care which produced it.

**Prices note.** Stooq is still implemented but is bot-gated behind a JS check, so Alpha Vantage
is the default. `PRICES_BACKEND` switches it if Stooq ever un-gates.

### What every client inherits

`BaseClient` gives each source the same behaviour:

- **Throttle** — a minimum interval between requests (`0.15s` default; SEC `0.11s` to stay
  under 10 req/s; prices `1.3s` for free-tier limits)
- **Retry with exponential backoff** — via `tenacity`, only on genuinely retryable failures
  (HTTP 429, 5xx, and transport errors). A 404 fails immediately rather than burning retries.
- **Freshness cache** — a source already landed recently is skipped, so re-runs don't
  re-consume a daily quota
- **Landing** — `_land(name, payload)` writes to `data/raw/<source_name>/<name>.<ext>`

**The landing zone is anchored to the repo, not to the process.** `raw_root()` resolves against
`ingestion/`'s own location rather than the working directory. It used to default to a relative
`"data/raw"`, which cost a whole backfill: the hub starts its market API with
`cwd=dashboard_hub/`, that API's backfill worker calls straight into these clients, and Ferrari's
1.3 MB of filings landed in `dashboard_hub/data/raw/` where `load_raw.py` never looks. The
request reported success, `RACE` joined `companies.yml` and the dbt seed, and the warehouse held
**zero facts** for it — a failure with no error anywhere. An explicit absolute `RAW_DATA_DIR` is
still honoured as given; a relative one now resolves against the repo.

### Surviving a source that half-answers

A feed that is simply down is easy — the retry handles it. The failures that cost real data are
the ones that return HTTP 200 and less than you asked for, and the World Bank does all of them.
What the client does about each:

| Failure | What it looks like | Handling |
|---|---|---|
| Whole-world pull times out | `ReadTimeout` on a 16-year, 265-entity request | Paged at 1,000 rows with a 90s timeout; a page that fails after retries ends the walk and **keeps** what it collected rather than discarding the indicator |
| One indicator retired or renamed | Exception mid-loop | Caught per indicator — the other three still land; the run only fails if *nothing* landed |
| An entity is not a country | `countryiso3code: ""` on aggregates (world, income bands, regions) | Kept in the landed payload for audit, dropped in staging — the blank passes a `not_null` test, so the filter is explicit |
| Indicator rejects a query shape | `NY.GDP.MKTP.KD.ZG` answers a flat **400** to `mrnev=1` | The live reader retries a different shape — a short date window — instead of retrying the rejected one, and reduces to the newest year per country |
| A country has no series | Silent absence from the response | Recorded as `empty_countries` in the landed envelope and logged, so a gap is a fact about the source rather than a mystery |
| Taiwan | Not a World Bank member; asking by code errors the whole request | Dropped from the request, added back by hand in the country reference |

The same posture applies at read time: the desk that consumes this treats a warehouse covering
13 countries as *no answer* rather than a small one, and goes to the source.

### Adding a new source

1. **Write the client** in `ingestion/`, subclassing `BaseClient`:

   ```python
   from .base_client import BaseClient


   class MySourceClient(BaseClient):
       source_name = "my_source"  # -> data/raw/my_source/
       base_url = "https://api.example.com/v1"
       min_interval_s = 0.5  # respect their rate limit

       def fetch_thing(self, arg: str) -> dict:
           payload = self._get(f"/things/{arg}").json()
           self._land(f"thing_{arg}", payload)
           return payload


   def main() -> None:
       from .config_loader import bootstrap

       bootstrap()
       with MySourceClient() as client:
           client.fetch_thing("abc")
   ```

   `main()` is the required entrypoint — the pipeline and Dagster both invoke it.

2. **Add a parser** in `load_raw.py` — a `parse_my_source() -> pd.DataFrame` function returning
   a tidy frame, then register it in `load_all()` so it lands as a `raw.*` table.

3. **Declare the raw table** in `dbt/models/staging/_sources.yml` under the `raw` source.

4. **Add a staging model** `dbt/models/staging/stg_my_source__thing.sql` — cast, rename, clean.
   No business logic; that belongs in `intermediate/`.

5. **Wire it into Dagster** in `orchestration/dagster_pipeline.py`: add an `@asset` calling
   `_run_extractor(context, my_source_client, "my_source")`, add the raw table to `RAW_TABLES`,
   and add the asset to both the `raw_tables` `deps` list and `Definitions(assets=[...])`.

6. **Commit a CI fixture** at `dbt/seeds/ci_raw/my_source.csv` so CI keeps building offline,
   and register its column types in `dbt_project.yml` under `seeds.kubera_edw.ci_raw`.

7. **Add tests** in `tests/` — mock the HTTP with `respx`, and add a malformed-response case to
   `test_malformed_responses.py`.

If the source needs a key, add it to `.env.example` and read it via
`config_loader.api_key("MY_KEY")`, which returns `None` for unset **or** placeholder values.

---

## dbt layers

Data moves through four schemas, each with one job. The layer boundaries are enforced by
materialization and naming, not convention alone.

```
raw.*            loaded by Python, never written by dbt
  └─ staging.*        views  — cast, rename, clean. 1:1 with a raw table. No joins, no logic.
       └─ intermediate.*  views  — the hard logic. Joins, pivots, dedup, FX fill.
            └─ marts.*        tables — conformed dimensions + facts. What BI reads.
```

| Layer | Materialization | Models | Rule |
|---|---|---|---|
| `staging` | view | 6 | One per raw table. Rename and cast only. |
| `intermediate` | view | 3 | Business logic lives here and nowhere else. |
| `marts` | **table** | 8 | 4 dimensions + 4 facts. The only layer BI queries. |
| `snapshots` | table | 1 | SCD2 history of the company universe. |

### Marts — the star schema

**Dimensions** (conformed, shared across facts):

| Dimension | Grain | Notes |
|---|---|---|
| `dim_company` | one row per company **version** | SCD2 — `is_current` flags the live row |
| `dim_date` | one row per calendar day | 2000-01-01 → 2031-01-01. **Calendar attributes only.** |
| `dim_country` | one row per country | **every country the World Bank publishes**, not only those holding an issuer; carries capital-city coordinates and `has_issuer` |
| `dim_currency` | one row per currency | ISO code, name, minor-unit digits |

**Facts:**

| Fact | Grain | Joins to |
|---|---|---|
| `fact_financials` | company × period (FY or Q) | `dim_company`, `dim_date`, `dim_currency` |
| `fact_market_prices` | company × trade date | `dim_company`, `dim_date` |
| `fact_macro_indicators` | country × year | `dim_country`, `dim_date` |
| `fact_gold_price` | date only | `dim_date` |

`dim_date` carries **calendar** attributes only — no fiscal columns. The universe spans five
distinct fiscal calendars (Sep, Jan, Jun, Mar, Dec year-ends), so a shared fiscal column would
be wrong for most companies. Fiscal period travels on the fact instead.

`fact_gold_price` joins only on `dim_date` by design — it is a single global series, a
cross-cutting benchmark rather than a per-holding measure.

**`dim_country` covers the world, not the portfolio.** It used to be built from the distinct
country codes in `seed_companies`, which meant `fact_macro_indicators` held 13 countries and
208 rows — enough to annotate a holding, not enough to answer *how does this government compare
to its peers*, which is the only reason to carry macro data at all. It is now the union of the
countries with an issuer and the countries the World Bank publishes: **211 countries, 3,376
macro rows**. `has_issuer` narrows it back to the portfolio for anything that wants the old
view, and the country_regions seed still wins on region naming where it has an opinion.

### Seeds

| Seed | Rows | Purpose |
|---|---|---|
| `seed_companies` | 38 | Generated from `companies.yml` by `generate_seeds.py` — never hand-edited |
| `seed_concept_map` | 24 | Maps XBRL tag → canonical concept, with priority. **The key to cross-taxonomy comparability.** |
| `country_regions` | 15 | ISO3 → country name, region, sub-region |
| `currency_names` | 14 | ISO → currency name, minor-unit digits |
| `ci_raw/*` | 6 files | Committed raw fixtures so CI builds the full DAG with no network |

### Tests

`dbt build` runs **96 nodes** including 65 schema tests, 3 unit tests, and 4 custom data tests:

| Test | Asserts |
|---|---|
| `assert_one_current_company_version_per_ticker` | SCD2 never produces two live rows for one ticker |
| `assert_usd_reporters_rate_is_one` | USD reporters get exactly `rate_per_usd = 1` |
| `assert_fx_currencies_are_modelled` | Every reporting currency in use has FX coverage |
| `assert_quarterly_reconciles_to_annual` | Four quarters ≈ the annual figure (warn-level) |

---

## Orchestration

Dagster models the whole pipeline as **one asset graph** — 41 assets, so the UI shows real
lineage from "SEC EDGAR companyfacts" all the way through marts, rather than one opaque
"run dbt" box.

```
extract (6 source assets)  →  load (6 raw table assets)  →  dbt (28 model/seed/snapshot/test assets)
```

| Piece | Detail |
|---|---|
| Extract assets | One `@asset` per source, `RetryPolicy(max_retries=3, delay=30, EXPONENTIAL)` |
| Seed asset | `dbt_seed_files` regenerates `seed_companies.csv` from `companies.yml` |
| Load asset | `raw_tables` — a `@multi_asset` emitting one asset per raw table |
| dbt assets | `@dbt_assets` reads the manifest, so every model/seed/snapshot/test is its own node |
| Job | `kubera_refresh` — full refresh, selection `*` |
| Schedule | `0 6 * * *` — 06:00 daily, **`DefaultScheduleStatus.STOPPED`** so it never auto-starts on import |
| Sensor | `kubera_run_failure_sensor` logs job failures for alerting/triage |

A source blocked on a missing API key is logged and reported as **zero records rather than
raised** — the pipeline still delivers every source it can, instead of one missing key taking
the whole warehouse down.

```bash
make orchestrate    # Dagster UI at http://localhost:3000
```

> `orchestration/dagster_pipeline.py` deliberately has **no** `from __future__ import annotations`.
> Dagster resolves the `context` parameter's annotation at runtime; PEP 563 would turn it into a
> string and the `@asset` decorator would reject it.

---

## Deployment

The same dbt project builds against three targets, selected by `--target`:

| Target | Adapter | Location | Used for |
|---|---|---|---|
| `dev` | Postgres | `localhost:5432`, cluster in `data/pgdata` | Local development |
| `ci` | DuckDB | `dbt/target/ci.duckdb` | Offline CI + `make demo` |
| `prod` | Postgres | Any server via `$POSTGRES_*` | Hosted warehouse |

**The warehouse is PostgreSQL.** `dev` and `prod` differ only in which server they point at —
same models, same SQL, same schemas — so promoting from this laptop to a hosted server is a
change of host and nothing else, and the SQL stays plain enough to lift into Snowflake or
Databricks after that. `ci` stays on DuckDB so `make demo` builds from committed fixtures with
no network, no credentials and no server to start.

`load_raw.py` picks its writer from `LOAD_TARGET` — `postgres` by default, `duckdb` only for the
offline `ci` path — so the Python loader and dbt stay pointed at the same place.

### Local

```bash
make db-up             # start Postgres (first run also initialises the cluster)
make pipeline          # extract -> seeds -> load -> dbt build
```

There is no system Postgres to install and no Docker required: `pgserver` ships a real
PostgreSQL 16 build as a Python wheel, and `scripts/local_postgres.py` runs it against a data
directory in `data/pgdata` (gitignored). `docker-compose.yml` still defines an equivalent
`warehouse` service if you would rather use containers — both read the same `POSTGRES_*`
variables, so nothing else changes.

### Hosted

Point `.env` at the server (`POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB`, `PGSSLMODE=require`), then:

```bash
make prod
```

### Containers

```bash
docker compose up -d
```

| Service | Image | Port | Role |
|---|---|---|---|
| `warehouse` | `postgres:16` | 5432 | Postgres warehouse, healthchecked, persistent volume |
| `orchestrator` | built from `Dockerfile` | 3000 | Dagster, `DBT_TARGET=prod` |
| `bi` | `metabase/metabase` | 3001 | Optional BI alternative to Streamlit |

The Dockerfile bakes `dbt parse` into the image, because `@dbt_assets` needs `manifest.json` at
**import time** to build the asset graph — generating it at container start would make the code
location fail to load on a cold boot.

### CI

`.github/workflows/ci.yml` runs two jobs:

1. **lint-and-test** — `ruff check`, `ruff format --check`, `pytest tests/ -v`
2. **dbt-build** — `dbt deps`, `dbt seed --target ci`, `dbt build --target ci`

The second job builds the **entire DAG offline** from the committed `ci_raw` fixtures. No secrets,
no network, no flaky external APIs in CI.

---

## Investment Research

```bash
make hub            # http://localhost:5173
```

**Hub and spoke.** The hub is a Vite/React app; every dashboard is an independent Streamlit
server on its own port, embedded in the hub through the Vite dev proxy. One command starts
both halves and Ctrl+C stops them together.

Navigation is two levels — the top bar holds **sections**, and each section holds its
**dashboards**:

| Desk | Unit of analysis | Views |
|---|---|---|
| **Markets** | a security | Stock Explorer, with Sectors below it |
| **Companies** | an issuer | Company Explorer |
| **World** | an economy | Governments · Trade · Sectors · Energy |
| **Portfolio** | a set you assembled | Portfolio Analytics *(building)* |
| **Dashboards** | — | The embedded reports, as a card index |

Each desk divides by **what a row means**, which is what makes placement obvious rather than
arbitrary. Markets is about securities; World is about economies. Those were one desk until
World outgrew it — at 1,061 lines against the Explorer's 588 it was the largest surface in the
app while being reachable only through a tab inside another one.

Two pieces of the hub are shared rather than repeated, because they were repeated first and it
showed. `<Ruled>` is the one labelled hairline — it had four implementations whose top margins
had drifted to 12px and 14px for the same gesture, and one page borrowed another page's class,
inheriting a margin tuned for a container it was not in. `useFetch` is the one request effect:
make an `AbortController`, raise a loading flag, call, catch, check `err.name` against
`'AbortError'`, lower the flag, return the abort. That appeared **fifteen times across eight
files**, with the abort guard in eleven of them — eleven chances to omit it and set state on an
unmounted view. It is now three, all of them genuinely different behaviour: two trailing-edge
debounced searches and one poller.

The guard is the reason it earns a hook rather than a convention. Aborting a request rejects its
promise, so a view navigated away from mid-flight lands in the `catch` like any real failure;
without the check it renders an error for a request nobody was waiting for. `useFetch` also
takes `skip`, which is what lets the World desk hold back the energy and trade requests until
their tab is the one on screen.

Each live desk runs its own **tape** — the scrolling quote strip under the masthead — carrying
that desk's subject rather than one global set of symbols:

- **Markets** is the US session and what a securities desk watches beside it: the three
  benchmarks, breadth (Russell 2000), volatility (VIX), the risk-free rate, the dollar it is all
  priced in, and the risk assets.
- **Companies** runs the largest issuers by **ticker** — on a desk whose whole subject is issuers, the symbol is what a reader scans for, and it fits more of the tape on screen.
- **World** runs ten national benchmarks and the four major currency pairs, each under its flag.

They were not always distinct. When World was promoted out of Markets it took the national
indices and the FX crosses with it, and half of what was left on Markets — FTSE, Nikkei,
EUR/USD, gold — now read as World's material sitting on the wrong desk. Only the S&P is shared
now, because it is genuinely the headline of both. Dashboards has no tape; a scrolling quote
strip over a list of reports would be noise.

A tape entry may name an `emblem` as `logo:TICKER` or `flag:ISO3`, kept separate from the quote
symbol because the two are often not the same thing — the Nikkei's mark is Japan's flag, not
`^N225`. Only World uses it. Company marks were tried on the Companies tape and taken off
again: at 13px on a moving strip a logo crowds the symbol without identifying it. They stay on
the grid, where the cards hold still and the marks have room.

**Dashboards** is the index of embedded surfaces. Every Streamlit page lives there as a card;
clicking one opens it in place. It exists because those pages are a different kind of thing —
their own processes, their own framework, operational rather than interactive — and mixing them
into the native desks made both harder to navigate.

Four of the five are **workspaces** rather than indexes. An index holds sheets you open, read
and leave, so a card grid is right for it — that is Dashboards. Markets, Companies, World and
Portfolio are live and stateful — browse, open, compare, hand off — so their views switch in
place and keep their state, which
is what `"layout": "workspace"` declares in the registry.

```
localhost:5173  hub (Vite)
   /                          all sections
   /s/portfolio               one section, listing its dashboards
   /s/portfolio/allocation    one dashboard, embedded

        ──proxy──▶  /d/allocation          ──▶ localhost:8511
                    /d/fundamentals        ──▶ localhost:8512
                    /d/fx-impact           ──▶ localhost:8513
                    /d/macro-overlay       ──▶ localhost:8515
```

`/d/*` is reserved for the proxy, so the hub's own routes live under `/s/*` and the two never
collide. A dashboard marked `"kind": "native"` is a React page the hub renders itself rather
than a service it embeds — **Stock Explorer**, **World** and **Company Explorer** are the
three. They read `/api/market/*`, served by
[`market_api.py`](dashboard_hub/market_api.py) (stdlib HTTP, no web framework), because Yahoo
rejects browser requests that lack a session cookie and crumb. Because each spoke is its own process, a dashboard can be rebuilt, restarted or
swapped for a different framework without touching the hub or any sibling dashboard.

The seven dashboards under **Portfolio**, **Companies** and **Markets** are built. The four
under **Risk**, **ESG** and **Warehouse** are registry entries with no process behind them yet
— their page says so and prints what it will take to wire them up.

#### World

Two lenses over one globe, on the Markets desk.

**Governments** puts every country the World Bank publishes — 212 of them — on a rotatable
globe and in one table, coloured by whichever of five metrics you pick: equity market, CPI
inflation, GDP growth, unemployment, or the currency against the dollar. The point is the
disagreement between them. Japan's last inflation print is 3.17% and its GDP grew 1.19%, while
the yen lost 6.2% against the dollar and the Nikkei returned +59.7% — four numbers about one
country that a single chart cannot hold.

**Sectors** ranks the ten iShares global sector funds. Each holds names from every listed
market rather than one, which is what makes it a world league table and not a second reading of
the S&P; the regional funds beside it are all USD-denominated so both tables sit on one scale.

The globe is an **orthographic projection drawn in SVG**, not a 3D library and not a rotated
`<div>`. Every frame recomputes each country's position from its capital-city latitude and
longitude, culls the hemisphere facing away (`z < 0`), and paints what is left back to front.
That is what keeps the markers crisp, clickable and data-bearing while it turns. It spins on
its own until you take hold of it, then stays where you leave it, and honours
`prefers-reduced-motion`.

#### Marks and flags

Every company on the grid carries its logo and every country its flag, **desaturated at rest
and full colour under the cursor**. Colour is the loudest signal on these pages and it is
already spoken for — green for a gain, red for a loss — so three hundred brand marks at full
saturation would shout over every number. Greyed, they are something you reach for rather than
fight past.

Both go through `/api/market/logo` and `/api/market/flag`, which fetch once and write to
`data/image_cache/` with a 30-day TTL, then serve from disk. Proxying rather than hot-linking
is what makes the cache possible — otherwise the page fires 300 cross-origin requests at a
favicon service on every load. Logos resolve from the company's own domain, captured into
`companies.json` by the universe generator; the mark comes from Google's favicon service
(128–180px for most listed companies) with DuckDuckGo as the fallback. Clearbit was the obvious
choice here and no longer resolves at all. A company neither service has falls back to a
lettermark, which reads as deliberate rather than as a hole.

#### One page, any currency

An ADR trades in one currency and files in another, and Yahoo builds some of its
ratios straight across the two without converting. Ferrari's NYSE line comes back with a
price/sales of **9.59** and an EV/EBITDA of **28.76**; its own Milan line reports **8.29** and
**24.93**. The gap is exactly EUR/USD — a dollar numerator over a euro denominator.

Those figures used to be **withheld** on the detail page, which was the cautious answer and the
wrong one: the information was recoverable all along. They are now recomputed from the
underlying quantities with both halves put into one currency:

| | Yahoo (RACE) | Kubera | Milan line |
|---|---|---|---|
| P/S | 9.59 | **8.33** | 8.29 |
| EV/EBITDA | 28.76 | **25.00** | 24.93 |
| P/B | 16.73 | **14.53** | — |

Enterprise value is rebuilt rather than converted — Yahoo's own is mixed, market cap in one
currency plus net debt in another — by backing net debt out against its cap and converting that.

There is a **fallback** for when Yahoo's `info` omits revenue, EBITDA or book value, which it
does intermittently: its published ratio is the true one multiplied by the rate between the two
currencies, so dividing that back out is exact and needs only the rate. Both routes agree to
three figures. This is not hypothetical — the direct route worked on a scripted call and left
the live page showing dashes ten minutes later.

A **currency picker** sits above the KPI grid, offering the majors plus the listing's own two,
marked *traded* and *reported*. It moves every level on the page — KPIs, statements, the filed
panel — and by construction leaves every multiple alone:

> Ferrari at $70.5bn / €61.3bn / ¥11,118bn market cap, with P/B 14.53, P/S 8.33 and EV/EBITDA
> 25.00 in all three.

That invariance is the correctness property, and it is what the tests assert: a ratio is
dimensionless once its two halves share a unit. A rate Yahoo has no pair for blanks the figures
that depend on it rather than leaving them unconverted.

#### Sorting the grid

Return, revenue, profit, revenue growth, profit growth. The two **level** sorts rank on
USD-converted figures, never the reported ones — Toyota books ¥50,685bn against Apple's $467bn,
and sorting raw numbers ranks by how small a currency's unit is. The conversion uses Yahoo's
`financialCurrency`, **not** `currency`: for an ADR those differ, and Toyota's TM trades in USD
while filing in JPY. Getting that wrong put Toyota top of the revenue ranking at "$50,685bn".
Growth needs no conversion — a percentage is currency-neutral — so those two sort on what was
filed.

> Ranked by revenue: Amazon $776bn, Walmart $725bn, Apple $467bn, UnitedHealth $450bn.
> By profit: Alphabet $244bn, NVIDIA $160bn, Amazon $135bn.

The figures are trailing twelve months, captured into `companies.json` at build time rather
than fetched per card — 300 Yahoo profile calls is not a page load. Re-run `make company-universe`
to refresh them.

#### The four lenses

**Governments** is the globe and the comparison table — inflation, growth, unemployment, currency
and equity market, for 212 countries. Opening a country (click the globe, or a row) replaces the
table with its full detail: purchasing power, what it trades, who with, and its news.

**Trade** answers *who buys from whom*. Pick a reporting country and the world recolours around
it — green where that country sells more than it buys, red where it buys more — with marker size
carrying how much trade there is at all. Bilateral flows come from **World Bank WITS**, which
republishes UN Comtrade: one request returns a reporter's trade with all 222 partners in a year,
both directions. WITS mixes aggregates (`WLD`, `EAS`, `NAC`) into the same ISO3 namespace as real
countries, so `countries.json` is used as the allow-list — otherwise "the world" tops every
ranking. Values arrive in thousands of USD.

> The United States sold $2.06T and bought $3.37T in 2022 — a $422bn deficit with China, $135bn
> with Mexico, and a $37bn surplus with the Netherlands.

**Sectors** ranks the ten iShares global sector funds, plus the same window by region.

**Energy** carries crude, both gas benchmarks (Henry Hub and Dutch TTF price the same molecule
either side of the Atlantic and rarely agree), refined products, the metals, and the GSCI. The
chart is **rebased to 100** rather than absolute: crude trades near $80 a barrel and gas near $3
an MMBtu, so on a shared price axis the gas line lies flat and hides the fact that it is the one
moving differently. Levels are in the table underneath, which is where a price belongs.

#### Gold as the unit of account

Every figure on this desk is quoted in dollars, and the dollar is not a fixed rule — it is one of
the things being measured. A market "up 20%" against a currency that lost ground has not
necessarily bought its holders anything.

So opening a country draws its currency three ways, all rebased to 100: **in gold**, **against
the dollar**, and **the dollar in gold** — so the benchmark is shown as a measured thing rather
than as the ruler. Gold is used because it is the one asset with a continuous price in every
currency going back further than any of these governments' current monetary regimes. This is not
a claim that gold is stable; it is that gold is *independent* — no country being compared issues
it, so it cannot flatter or punish one of them.

> Over five years the yen fell 31.8% against the dollar — and 69.5% against gold, because the
> dollar itself fell 55.3%. Two of those three numbers are invisible on a USD-denominated page.

#### What a country trades

Composition comes from five World Bank indicators per direction — manufactures, fuel, food, ores
and metals, agricultural raw. Not a full commodity breakdown, but it answers the question people
actually ask of a country: does it sell things it makes, or things it digs up?

> Saudi Arabia: 79.4% fuel. Brazil: 40.7% food. Germany: 84.1% manufactures. Japan sells 80.6%
> manufactures and buys 19.6% fuel — which is why Australia and the UAE are among its largest
> suppliers.

Ten indicators for **one** country took eleven minutes of small, slow round trips; ten indicators
for **every** country takes about a minute and then answers instantly for all of them. Since the
desk lets a reader click any country on a globe, that cost is paid once — in a background thread
at API start — not per click. It caches to `data/trade_cache/` for a week.

**Coastlines** come from Natural Earth's 110m land layer (public domain), thinned with
Ramer–Douglas–Peucker from 5,143 points to 1,492 and bundled as
[`land.json`](dashboard_hub/hub/src/components/land.json) — 22 KB. They are **stroked, not
filled**: a filled landmass would have to be closed along the limb wherever a continent runs
off the edge, and it would put a slab of tone on a page built out of hairlines. Where a coast
crosses the horizon the path is cut at the exact crossing, found by bisecting on the same
`project` the rest of the globe uses, so the clip can never disagree with the projection. Long
segments are subdivided first, because a straight line in lon/lat is not a straight line on a
sphere — and a segment with both ends on the near face can still pass behind the globe in
between, which would otherwise draw a chord across the visible disc.

```bash
python -m scripts.generate_land_outline    # only to change the tolerance
```

Three feeds meet on this page and they reach different distances, so the desk says which is
which rather than blending them:

| Layer | Source | Cadence | Covers |
|---|---|---|---|
| Macro | Warehouse (`fact_macro_indicators`), else World Bank live | Annual, 1–2 years behind | 212 countries |
| FX | Yahoo, live | Live | 38 currencies |
| Equity markets | Yahoo, live | Live | 29 local benchmarks |
| Geography | [`countries.json`](dashboard_hub/countries.json) | Static | 212 countries |

**Why macro can come from two places.** `fact_macro_indicators` is the right source and the
fast one. But a warehouse built before the ingestion went worldwide — or a deployment still on
the previous prod schema — carries only the dozen countries that hold an issuer, and a globe
with thirteen dots on it is not a world view. So the desk checks: fewer than 40 countries in
the marts and it reads the World Bank live instead, caching the result to
`data/world_macro_cache.json` so a restart does not re-pull it. The caption under the table
names whichever answered.

The geography is a bundled file rather than a warehouse query for the same reason `sectors.json`
and `companies.json` are — the page has to draw on a clean checkout with no dbt run behind it.
Regenerate it with:

```bash
python -m scripts.generate_country_reference
```

#### Company Explorer

The Companies desk opens on a grid of ~300 listings — every constituent of every editorial
sector in [`sectors.json`](dashboard_hub/sectors.json), plus every issuer the warehouse
carries filings for, badged. Opening one gives its price history over any window, the
valuation multiples, a long-run quarterly revenue chart, and the income statement, margins,
balance sheet and cash flow, annual or quarterly. The search box is not limited to the grid:
a ticker it does not recognise is looked up live and opens the same page.

Each statement opens on the handful of lines it is actually read for, with the rest one click
behind a button that says how many are there — stacked in full, the four statements run to
forty rows and bury the figures most readers came for.

**Revenue back to 2008.** Yahoo publishes five quarters, which is not a history. So the
revenue chart reads the filer's own XBRL facts from SEC EDGAR at request time — the same
source the warehouse is built from, one company at a time — and gets seventy-odd quarters for
most US filers, windowed to 3, 5 or 10 years or all of it. Four things have to be fixed on
the way through, all in [`lib/filings.py`](dashboard_hub/lib/filings.py):

| Problem | What the raw facts do | Fix |
|---|---|---|
| Periods are unlabelled | `frame` is sparse — NVIDIA has 12 framed quarters against 66 real ones — and revenue tags change over a filer's life | Classify by how long the period actually ran |
| No fourth quarter | A 10-K filer publishes three 10-Qs and an annual report | Derive it: the year less the three |
| Banks have no top line | JPMorgan tags `Revenues` only to 2014; a bank earns interest and fees, not sales | Compose it: net interest income + noninterest income, filling gaps only |
| Two currencies | Toyota carries 27 years of revenue in JPY **and** 4 years of the same line in USD | Pick the currency the most recent filings use, once for the whole series |
| Lines tagged apart | Revenue and net income often carry start dates a day apart | Join them on the period end |

Both cadences are built and both are offered. Which one opens depends on the filer: a US
filer reads best quarterly, while a foreign private issuer files annually on Form 20-F and has
no quarters at all — Yahoo offers five, but its own filings carry eighteen annual years, and
eighteen years beats five quarters. Ford's chart runs from 2008 and shows both crises;
Toyota's shows the 2009 loss.

This needs `SEC_EDGAR_USER_AGENT` set, the same variable the pipeline uses. Without it the
chart falls back to the warehouse's own rows and then to Yahoo's, and says underneath which
one answered. A listing that files nothing at all — an index, a fund, a currency — says that
rather than reporting an empty chart.

For an issuer indexed in the warehouse, a second panel sits below the statements: the **filed** figures from
`marts.fact_financials`, traceable to a CIK and a taxonomy, with each year converted at the
rate on its own period end. They are kept in their own panel rather than merged — the two
sources are on different bases and blending them would hide that.

#### Backfill on request

A company that is not one of the 38 gets that panel replaced by a request. Queueing it adds
the name to the warehouse for good: SEC is asked what kind of filer it is, an entry is
appended to `companies.yml`, its filings are landed, and dbt rebuilds. Afterwards it is a
holding like any other — FX-normalised, dbt-tested, and present in the allocation, FX and
macro views rather than only on the page that fetched it live.

```bash
make backfill TICKER=NVDA     # one company, start to finish
make backfill                 # drain whatever the desk has queued
```

The queue is [`data/backfill_queue.json`](data/backfill_queue.json), written by the market API
and read by a Dagster sensor that launches `backfill_job` per request. The sensor needs the
daemon (`make orchestrate`); without it the same work runs from the make target above, which
is the identical code path.

**The warehouse takes one writer at a time.** DuckDB locks the file, so anything holding it
open blocks a rebuild — and the hub used to hold it open in five processes at once, which
meant a backfill could never run while the desk was up. Both readers now open the file per
query and close it again ([`lib/db.py`](dashboard_hub/lib/db.py),
[`lib/warehouse.py`](dashboard_hub/lib/warehouse.py)); results are cached, so this costs a few
milliseconds a few times an hour. On Postgres the constraint does not apply and the engine is
pooled as before.

Names and classifications for the grid come from
[`companies.json`](dashboard_hub/companies.json), resolved once at build time because ~300
profile lookups is not a page load. Regenerate it after editing `sectors.json` or
`companies.yml`:

```bash
make company-universe
```

The desk works with no warehouse at all — the filed panel is what a clean checkout gives up,
not the page.

[`dashboard_hub/dashboards.json`](dashboard_hub/dashboards.json) is the single source of
truth. The same file drives the Streamlit processes `run_local.py` spawns, the Vite proxy
table, the hub's navigation, and the palette the spokes are themed with — so adding a
dashboard means editing one file, then creating `dashboard_hub/dashboards/<module>/app.py`.
Entries marked `"status": "planned"` appear in the nav with no process behind them yet.

### House style

Engraved stationery: bone stock, black ink, hairline rules, **Copperplate** set in caps with
wide letterspacing, and gold as the only accent. It inverts to black stock and bone ink from
the switch in the top bar — the choice is remembered, and it is stamped on `<html>` before
first paint so a dark-mode reader never gets a white flash.

The embedded dashboards invert with it. Streamlit fixes its base theme when the process
starts, so the hub passes `?theme=` on the iframe and
[`lib/ui.py`](dashboard_hub/lib/ui.py) applies the matching stock as a CSS overlay. Chart
series stay inside the gold / silver / bronze family in both stocks — separated by lightness
and the warm/cool axis rather than hue, which is why more than about five series on one chart
is harder to read here than a rainbow scale would be. That cost is noted in
[`lib/theme.py`](dashboard_hub/lib/theme.py).

There is one joke in here. The house style — bone stock, black ink, Copperplate in caps — is
Paul Allen's business card, and has been since the first commit, so that is where the contact
details live: **double-click the KUBERA mark** in the top bar and the card flips out over a
blurred terminal. Click anywhere off it, or press `Esc`, and it flips away. The 404 page knows
what film this is too.

| Command | Does |
|---|---|
| `make hub` | Hub + every dashboard, one terminal |
| `make hub-dashboards` | Only the Streamlit dashboards, no hub UI |
| `npm run dev:web` | Only the hub, if the spokes are already running |

The hub reuses the project venv (`make setup`) — there is no second Python environment.
Node 18+ is required for the hub UI only; the dashboards themselves need no Node.

---

## Dashboards

Every dashboard is its own Streamlit process, embedded by the hub. They share
`dashboard_hub/lib/` — one warehouse connection with a 5-minute cache, one set of queries, one
chart theme — so a number means the same thing on every page. Every chart ships its underlying
table, so an analyst can sanity-check any figure they don't believe.

| Dashboard | Section | Shows |
|---|---|---|
| **Portfolio Allocation** | Portfolio | Equal-weighted diversification by country, sector, currency, region |
| **Fundamentals** | Companies | Revenue growth, margins and leverage — all USD-normalized |
| **FX Impact** | Companies | What currency movement did to reported results for non-USD reporters |
| **Macro Overlay** | Markets | GDP growth, inflation, unemployment, and the gold benchmark |

Every mart has an **empty state** — if a table has zero rows the dashboard explains why and
prints the command that fixes it, rather than crashing.

| | |
|---|---|
| ![Allocation](docs/screenshots/01_portfolio_allocation.png) | ![Fundamentals](docs/screenshots/02_fundamentals.png) |
| ![FX impact](docs/screenshots/03_fx_impact.png) | ![Macro overlay](docs/screenshots/04_macro_overlay.png) |

These are **rendered, not screenshotted**. `scripts/generate_screenshots.py` queries the live
warehouse, rebuilds each chart with Altair, and rasterizes the Vega-Lite spec via `vl_convert` —
so they cannot drift from the data. Regenerate with `make screenshots`.

The same run also writes **card thumbnails** to `dashboard_hub/hub/public/thumbnails/<id>.png`,
keyed by dashboard id so the file the hub asks for and the file the script writes cannot drift
apart. The Dashboards desk draws these on its cards — greyed at rest, full colour on hover, the
same rule the company marks follow.

They are **rendered from the chart, not screenshotted from the running page**. A capture of a
live Streamlit app shown at 300px is mostly chrome, sidebar and unreadable axis text, where the
chart is the thing the dashboard exists for. It also means no browser, no running dashboards and
no 150 MB of Chromium in the toolchain — the script reads the warehouse and writes a PNG. A
dashboard with no entry in `THUMBNAILS` simply has no image and its card falls back to the
numbered plate, which is what the two uncommissioned ones do; the script prints a warning if one
goes into service without a thumbnail.

Metabase is available as a containerized alternative (`docker compose up bi`, port 3001), but
Streamlit is the primary, reproducible deliverable.

---

## Coverage universe

38 companies, edited in **one place**: [`ingestion/config/companies.yml`](ingestion/config/companies.yml).
`generate_seeds.py` regenerates the dbt seed from it, so the universe is never defined twice.

Benchmarks: **SPY**, **ACWI**.

### United States — 10-K filers, us-gaap (9)

| Ticker | Company | Sector | Currency | FY end |
|---|---|---|---|---|
| AAPL | Apple Inc. | Technology | USD | 09-26 |
| CAT | Caterpillar Inc. | Industrials | USD | 12-31 |
| F | Ford Motor Co. | Consumer Discretionary | USD | 12-31 |
| JNJ | Johnson & Johnson | Healthcare | USD | 01-03 |
| JPM | JPMorgan Chase & Co. | Financials | USD | 12-31 |
| KO | Coca-Cola Co. | Consumer Staples | USD | 12-31 |
| MSFT | Microsoft Corp. | Technology | USD | 06-30 |
| PG | Procter & Gamble Co. | Consumer Staples | USD | 06-30 |
| XOM | Exxon Mobil Corporation | Energy | USD | 12-31 |

### Europe — 20-F filers (13)

| Ticker | Company | Country | Sector | Domestic | Reports in | Taxonomy |
|---|---|---|---|---|---|---|
| ASML | ASML Holding N.V. | Netherlands | Technology | EUR | EUR | us-gaap |
| AZN | AstraZeneca plc | United Kingdom | Healthcare | GBP | USD | ifrs-full |
| BP | BP plc | United Kingdom | Energy | GBP | USD | ifrs-full |
| DB | Deutsche Bank AG | Germany | Financials | EUR | EUR | ifrs-full |
| DEO | Diageo plc | United Kingdom | Consumer Staples | GBP | GBP | ifrs-full |
| GSK | GSK plc | United Kingdom | Healthcare | GBP | GBP | ifrs-full |
| HSBC | HSBC Holdings plc | United Kingdom | Financials | GBP | USD | ifrs-full |
| NVS | Novartis AG | Switzerland | Healthcare | CHF | USD | ifrs-full |
| SHEL | Shell plc | Netherlands/UK | Energy | GBP | USD | ifrs-full |
| SNY | Sanofi | France | Healthcare | EUR | EUR | ifrs-full |
| TTE | TotalEnergies SE | France | Energy | EUR | USD | ifrs-full |
| UBS | UBS Group AG | Switzerland | Financials | CHF | USD | ifrs-full |
| UL | Unilever plc | United Kingdom | Consumer Staples | GBP | EUR | ifrs-full |

### Asia-Pacific — 20-F filers (12)

| Ticker | Company | Country | Sector | Domestic | Reports in | Taxonomy |
|---|---|---|---|---|---|---|
| BABA | Alibaba Group Holding | China | Technology / Consumer | CNY | CNY | us-gaap |
| BHP | BHP Group Ltd. | Australia | Materials | AUD | USD | ifrs-full |
| BIDU | Baidu Inc. | China | Technology | CNY | CNY | us-gaap |
| HMC | Honda Motor Co. | Japan | Consumer Discretionary | JPY | JPY | ifrs-full |
| INFY | Infosys Ltd. | India | Technology | INR | USD | ifrs-full |
| JD | JD.com Inc. | China | Consumer Discretionary | CNY | CNY | us-gaap |
| KB | KB Financial Group | South Korea | Financials | KRW | KRW | ifrs-full |
| MUFG | Mitsubishi UFJ Financial Group | Japan | Financials | JPY | JPY | us-gaap |
| SKM | SK Telecom Co. | South Korea | Telecom | KRW | KRW | ifrs-full |
| SONY | Sony Group Corp. | Japan | Technology / Media | JPY | JPY | us-gaap |
| TM | Toyota Motor Corp. | Japan | Consumer Discretionary | JPY | JPY | ifrs-full |
| WIT | Wipro Ltd. | India | Technology | INR | INR | ifrs-full |

### Latin America — 20-F filers (4)

| Ticker | Company | Country | Sector | Domestic | Reports in | Taxonomy |
|---|---|---|---|---|---|---|
| AMX | America Movil SAB | Mexico | Telecom | MXN | MXN | ifrs-full |
| ITUB | Itau Unibanco Holding | Brazil | Financials | BRL | BRL | ifrs-full |
| PBR | Petroleo Brasileiro (Petrobras) | Brazil | Energy | BRL | USD | ifrs-full |
| VALE | Vale S.A. | Brazil | Materials | BRL | USD | ifrs-full |

**Domestic currency ≠ reporting currency** for 12 of these — AZN, BP, HSBC, NVS, SHEL, TTE, UBS,
UL, BHP, INFY, PBR, VALE. AstraZeneca is British but reports in USD; Unilever is British but
reports in EUR. The distinction is carried explicitly because getting it wrong silently corrupts
every converted figure.

`xbrl_taxonomy` is **verified from filings, not inferred** — a 20-F filer is not necessarily an
IFRS tagger. Six of the 29 foreign filers tag in `us-gaap`: ASML, BABA, BIDU, JD, MUFG and SONY.
Run `make universe` to re-validate every company against SEC EDGAR before editing
`companies.yml`.

**Universe at a glance:** 38 companies · 29 × 20-F and 9 × 10-K · 23 × `ifrs-full` and
15 × `us-gaap` · 13 countries · 11 currencies · 5 distinct fiscal year-ends.

---

## Configuration

Copy `.env.example` to `.env` and fill in what you need. Everything is read via `os.environ`;
nothing is hardcoded.

| Variable | Required for | Notes |
|---|---|---|
| `SEC_EDGAR_USER_AGENT` | SEC EDGAR | `"Name email@example.com"` — SEC rejects requests without it |
| `ALPHA_VANTAGE_API_KEY` | Prices + gold | Free tier ≈ 25 requests/day; caching covers the universe |
| `FRED_API_KEY` | FRED gold path | Free. Only needed if you pass an explicit `series_id`. |
| `PRICES_BACKEND` | optional | `alpha_vantage` (default) or `stooq` |
| `DUCKDB_PATH` | optional | Overrides the offline `ci` warehouse location |
| `POSTGRES_*` | warehouse | Host, port, user, password, db, schema. Defaults to the local cluster |
| `PGSSLMODE` | warehouse | `disable` locally, `require` against a server |
| `CENSUS_API_KEY` | US port trade | Free. Without it the US trade layer and its dbt models switch off |
| `RAW_DATA_DIR` | optional | Overrides `data/raw/` |
| `DBT_TARGET` | containers | `prod` in docker-compose |

`config_loader.api_key()` treats placeholder values (`your_`, `_here`, `change_me`, `xxx`) as
unset, so a half-filled `.env` fails cleanly instead of sending a literal `your_key_here` to
an API.

---

## Tech stack

Python 3.12 · httpx · tenacity · pandas · PyYAML · DuckDB · Postgres · dbt-core 1.11 ·
dbt-duckdb · dbt-postgres · dbt_utils · Dagster · Streamlit · Altair · pytest · respx · ruff · uv

---

## License

MIT — see [LICENSE.md](LICENSE.md).
