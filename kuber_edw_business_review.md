# KUBERA_EDW

**Global Asset Management — Enterprise Data Warehouse & BI Platform**
Project Specification, Architecture & Data Strategy Document

Prepared as a portfolio project demonstrating end-to-end data engineering and business intelligence capability in a buy-side asset management context: extraction from real public financial and macroeconomic data sources, transformation into a modeled enterprise data warehouse, and delivery of investment-grade analytics.

---

## Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Goals & Skills Demonstrated](#2-project-goals--skills-demonstrated)
3. [Business Framing: Kubera Global Asset Management](#3-business-framing-kubera-global-asset-management)
4. [Investment Universe & Strategy Logic](#4-investment-universe--strategy-logic)
5. [Data Sources & APIs](#5-data-sources--apis)
   - 5.1 [Source Reference & Documentation Links](#51-source-reference--documentation-links)
6. [Company Universe (Coverage List)](#6-company-universe-coverage-list)
7. [Technology Stack (All Free / Open-Source)](#7-technology-stack-all-free--open-source)
8. [Repository Layout](#8-repository-layout)
9. [Data Model: Facts, Dimensions & Grain](#9-data-model-facts-dimensions--grain)
10. [KPI & Metrics Framework](#10-kpi--metrics-framework)
11. [Data Cadence, Reconciliation & Known Limitations](#11-data-cadence-reconciliation--known-limitations)
12. [Build Roadmap / Phases](#12-build-roadmap--phases)
13. [Appendix: Assumptions](#13-appendix-assumptions)

---

## 1. Executive Summary

Kubera_EDW is a self-directed portfolio project that simulates the data infrastructure of a global asset management firm. It is designed to demonstrate, in a single repository, the same category of work performed during a private equity data/ETL internship: sourcing raw external data, building a governed ETL pipeline, modeling it into a warehouse suited for analytical querying, and producing business intelligence outputs that a real investment team would use to make decisions.

Unlike a generic "PE portfolio company" simulation, which requires private, non-public operational data that cannot be legally or practically sourced, Kubera is framed as an asset management firm holding large, disclosed public equity positions across multiple countries. This framing was chosen deliberately so that **the entire pipeline can run on real, freely available data** — company filings, macroeconomic indicators, market prices, and currency rates — with no synthetic placeholder data required for the core build.

## 2. Project Goals & Skills Demonstrated

- Show real ETL engineering: extraction from multiple heterogeneous public APIs, transformation/cleaning logic, and loading into a modeled warehouse.
- Show EDW / dimensional modeling skill: proper fact and dimension tables, slowly changing dimensions, conformed dimensions across data domains (company, country, time, currency).
- Show BI judgment, not just coding ability: the KPIs, schema, and dashboards should reflect what an asset management analyst actually needs to answer, not an arbitrary technical exercise.
- Show data quality thinking: reconciliation checks, handling of missing/irregular international filings, currency normalization.
- Show orchestration and reproducibility: a pipeline that can be re-run on a schedule, containerized, and verified with tests.
- Produce an artifact a hiring manager can open, run locally in minutes, and understand from the README without a walkthrough.

## 3. Business Framing: Kubera Global Asset Management

**Kubera Global Asset Management** (fictional) is modeled as an active, concentrated-position asset manager — a firm that takes meaningful, disclosed stakes in a defined universe of public companies across multiple regions, rather than passively tracking an index. This is closer in spirit to firms such as Elliott Management, Third Point, or the actively-managed arms of large asset managers, and it is the framing that best matches what public data can actually support.

**Why this framing, and not traditional buyout PE:**

- Traditional buyout PE requires private ownership data (internal transactions, private deal terms, leverage structuring) that is never publicly disclosed — any simulation of it requires inventing data, which weakens the "real data" story.
- An asset manager holding public positions stays inside a fully transparent, continuously-disclosed data environment for the life of the holding — no going-private gap, no invented deal terms.
- It naturally supports an international, multi-currency, multi-macro-regime narrative, which is the direction of the project.
- It maps to a broader, more commonly hired-for skill set (portfolio analytics, investment data, asset management BI) than a narrow PE-specific angle.

## 4. Investment Universe & Strategy Logic

Kubera holds positions across ~35–45 real, publicly traded companies spanning North America, Europe, Asia-Pacific, and Latin America, across a deliberate mix of sectors (technology, financials, industrials, energy, healthcare, consumer, materials). The business questions the warehouse must answer are:

- How is each holding performing, fundamentally, quarter over quarter or filing-period over filing-period?
- How is our overall portfolio allocated by country, sector, and currency exposure?
- How do currency movements affect our reported (USD-normalized) returns on international holdings?
- How does each holding's price performance compare to a relevant benchmark or its sector peers?
- What is the macroeconomic backdrop (GDP growth, inflation, rates) in each country where we hold a position, and how does it correlate with holding performance?
- Which positions are outperforming/underperforming their entry thesis, and by how much?

## 5. Data Sources & APIs

All primary data sources below are free and require no paid tier for this project's scope. Where an API key is required, it is free to obtain and has a generous rate limit for a project of this size.

| Source | Provides | Key Required | Notes / Access Pattern |
|---|---|---|---|
| **SEC EDGAR** (submissions & XBRL Frames API) | Company filings: 10-K/10-Q for U.S. domestic filers; 20-F/6-K for foreign private issuers (ADRs). Structured financial statement facts via XBRL. | No | Requires a descriptive User-Agent header identifying the requester. No published hard rate limit, but self-throttle (e.g. ~10 req/sec). |
| **World Bank API** | Country-level macro indicators: GDP, GDP growth, inflation (CPI), unemployment, FDI inflows, trade balance, going back decades. | No | REST, JSON/XML. Query by country ISO code + indicator code + year range. |
| **IMF Data API** | International financial stability indicators, government finance statistics, exchange rate regimes. | No | SDMX-based REST API; slightly heavier query syntax than World Bank. |
| **OECD API** | Cross-country indicators for OECD member states (subset of Kubera's country coverage). | No | Useful as a secondary/cross-check source for developed-market macro data. |
| **FRED** (Federal Reserve Economic Data) | U.S. macro indicators and rates; useful as the USD-denominated benchmark series against which other countries are compared. | Yes (free) | Very generous free-tier limits; simple REST/JSON. |
| **Exchange rate API** (Frankfurter / exchangerate.host) | Historical and current FX rates for currency-normalizing all non-USD holdings. | No | Needed for every non-U.S. holding's USD-adjusted return calculation. |
| **FRED — Gold Price series** (`GOLDAMGBD228NLBM`) | Daily LBMA gold fixing price (USD/troy oz), historical back to 1968. Useful as a macro hedge/benchmark indicator and inflation cross-check alongside CPI. | Yes (same free FRED key already in use) | No new signup needed if FRED is already wired up for U.S. macro data — just a different series ID on the same endpoint. |
| **metals-api.com** (backup/alternative) | Live and historical spot prices for gold, silver, and other metals, quoted in multiple currencies. | Yes (free tier) | Use only if a real-time/intraday spot price is needed instead of FRED's daily fixing price; free tier has a modest monthly request cap, so batch/cache calls. |
| **Stock price / fundamentals API** (Alpha Vantage, or Stooq for historical daily prices) | Daily close prices for return calculations, volatility, drawdown, benchmark comparison. | Alpha Vantage: yes (free) / Stooq: no | Alpha Vantage free tier is low-volume (historically ~25 requests/day) — batch and cache aggressively, or use Stooq for bulk historical daily prices without a key. |

**Design note:** every source above joins back to a common set of conformed dimensions: *company* (via ticker/CIK), *country* (via ISO-3166 code), and *time* (via fiscal period or calendar date) — this is what allows financial filing data, macro data, and market data to sit in the same warehouse and be queried together.

### 5.1 Source Reference & Documentation Links

Quick-reference for the actual docs each client will be built against. Verify these are still current before coding — API docs pages and terms move.

| Source | Docs / Reference URL | Auth Type |
|---|---|---|
| SEC EDGAR (submissions + XBRL Frames API) | https://www.sec.gov/edgar/sec-api-documentation | None (User-Agent header required) |
| World Bank API | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 | None |
| IMF Data API | https://www.imf.org/external/datamapper/api/help (simpler DataMapper API) — note: IMF retired its legacy `dataservices.imf.org` portal in Nov 2025 in favor of a new SDMX 3.0 API at data.imf.org; confirm the current REST docs there before building | None |
| OECD API | https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html | None |
| FRED API (incl. gold price series) | https://fred.stlouisfed.org/docs/api/fred/ | Free API key |
| Frankfurter (FX rates) | https://frankfurter.dev/ | None |
| exchangerate.host (FX rates, alternative) | https://exchangerate.host/documentation | Free API key (as of recent versions) |
| metals-api.com | https://metals-api.com/documentation | Free API key |
| Alpha Vantage | https://www.alphavantage.co/documentation | Free API key |
| Stooq (historical daily prices, no key) | https://stooq.com/db/h/ | None |

> Treat this table as a starting map, not gospel — confirm each URL resolves and each endpoint's current terms/rate limits directly before wiring a client to it.

## 6. Company Universe (Coverage List)

A working list of ~40 real, publicly traded companies across regions and sectors. U.S. companies are 10-K/10-Q domestic filers; non-U.S. companies listed are ones with U.S.-listed ADRs that file Form 20-F/6-K with the SEC (so all remain sourceable via EDGAR). This list is a starting universe — trim or extend it once the pipeline is working end-to-end on a smaller subset (recommended: start with 6-8 companies, then scale out).

### North America

| Company | Ticker | Country | Sector | SEC Filing Type |
|---|---|---|---|---|
| Apple Inc. | AAPL | United States | Technology | 10-K / 10-Q (domestic) |
| Microsoft Corp. | MSFT | United States | Technology | 10-K / 10-Q (domestic) |
| JPMorgan Chase & Co. | JPM | United States | Financials | 10-K / 10-Q (domestic) |
| Exxon Mobil Corp. | XOM | United States | Energy | 10-K / 10-Q (domestic) |
| Johnson & Johnson | JNJ | United States | Healthcare | 10-K / 10-Q (domestic) |
| Procter & Gamble Co. | PG | United States | Consumer Staples | 10-K / 10-Q (domestic) |
| Caterpillar Inc. | CAT | United States | Industrials | 10-K / 10-Q (domestic) |
| Ford Motor Co. | F | United States | Consumer Discretionary | 10-K / 10-Q (domestic) |
| Coca-Cola Co. | KO | United States | Consumer Staples | 10-K / 10-Q (domestic) |
| America Movil SAB | AMX | Mexico | Telecom | 20-F (foreign private issuer) |

### Europe

| Company | Ticker | Country | Sector | SEC Filing Type |
|---|---|---|---|---|
| AstraZeneca plc | AZN | United Kingdom | Healthcare | 20-F (foreign private issuer) |
| Unilever plc | UL | United Kingdom | Consumer Staples | 20-F (foreign private issuer) |
| BP plc | BP | United Kingdom | Energy | 20-F (foreign private issuer) |
| HSBC Holdings plc | HSBC | United Kingdom | Financials | 20-F (foreign private issuer) |
| GSK plc | GSK | United Kingdom | Healthcare | 20-F (foreign private issuer) |
| Diageo plc | DEO | United Kingdom | Consumer Staples | 20-F (foreign private issuer) |
| Sanofi | SNY | France | Healthcare | 20-F (foreign private issuer) |
| TotalEnergies SE | TTE | France | Energy | 20-F (foreign private issuer) |
| Shell plc | SHEL | Netherlands/UK | Energy | 20-F (foreign private issuer) |
| ASML Holding N.V. | ASML | Netherlands | Technology | 20-F (foreign private issuer) |
| Novartis AG | NVS | Switzerland | Healthcare | 20-F (foreign private issuer) |
| UBS Group AG | UBS | Switzerland | Financials | 20-F (foreign private issuer) |
| Deutsche Bank AG | DB | Germany | Financials | 20-F (foreign private issuer) |

### Asia-Pacific

| Company | Ticker | Country | Sector | SEC Filing Type |
|---|---|---|---|---|
| Toyota Motor Corp. | TM | Japan | Consumer Discretionary | 20-F (foreign private issuer) |
| Sony Group Corp. | SONY | Japan | Technology / Media | 20-F (foreign private issuer) |
| Honda Motor Co. | HMC | Japan | Consumer Discretionary | 20-F (foreign private issuer) |
| Mitsubishi UFJ Financial Group | MUFG | Japan | Financials | 20-F (foreign private issuer) |
| Taiwan Semiconductor Mfg. | TSM | Taiwan | Technology | 20-F (foreign private issuer) |
| SK Telecom Co. | SKM | South Korea | Telecom | 20-F (foreign private issuer) |
| KB Financial Group | KB | South Korea | Financials | 20-F (foreign private issuer) |
| Alibaba Group Holding | BABA | China | Technology / Consumer | 20-F (foreign private issuer) |
| JD.com Inc. | JD | China | Consumer Discretionary | 20-F (foreign private issuer) |
| Baidu Inc. | BIDU | China | Technology | 20-F (foreign private issuer) |
| Infosys Ltd. | INFY | India | Technology | 20-F (foreign private issuer) |
| ICICI Bank Ltd. | IBN | India | Financials | 20-F (foreign private issuer) |
| Wipro Ltd. | WIT | India | Technology | 20-F (foreign private issuer) |
| BHP Group Ltd. | BHP | Australia | Materials | 20-F (foreign private issuer) |

### Latin America

| Company | Ticker | Country | Sector | SEC Filing Type |
|---|---|---|---|---|
| Petroleo Brasileiro (Petrobras) | PBR | Brazil | Energy | 20-F (foreign private issuer) |
| Vale S.A. | VALE | Brazil | Materials | 20-F (foreign private issuer) |
| Itau Unibanco Holding | ITUB | Brazil | Financials | 20-F (foreign private issuer) |

**Important verification step:** tickers, filer status (10-K vs. 20-F), and even continued SEC registration can change over time (delistings, re-domestications, M&A). Before building against any of these, confirm current filer status directly on SEC EDGAR's company search (sec.gov/cgi-bin/browse-edgar) rather than assuming this list is still accurate at build time.

## 7. Technology Stack (All Free / Open-Source)

| Layer | Tool | Why |
|---|---|---|
| Extraction | Python (requests / httpx) | Simple, dependency-light HTTP calls to REST/XBRL/SDMX APIs. |
| Storage / Warehouse | DuckDB (dev) or Postgres (containerized) | Free, zero/low-infra, full SQL, handles millions of rows comfortably on a laptop. |
| Transformation / Modeling | dbt Core | Open-source; industry-standard for warehouse modeling, testing, documentation, and lineage. |
| Orchestration | Dagster (or Airflow) via Docker Compose | Free, local, schedules and monitors the pipeline; demonstrates production-style orchestration. |
| Containerization | Docker + Docker Compose | One-command reproducibility for anyone reviewing the repo. |
| CI | GitHub Actions (free for public repos) | Runs linting and dbt tests automatically on every push/PR. |
| BI / Presentation layer | Metabase (self-hosted, free) or a Streamlit app | Free dashboarding on top of the warehouse; no paid BI license needed. |
| Version control | Git + GitHub | Standard; repo is public-facing portfolio artifact. |

Nothing in this stack requires a paid tier, a cloud account, or a credit card. Everything runs locally via Docker Compose, which is itself part of the story: the project is fully reproducible by anyone who clones it.

## 8. Repository Layout

```
kubera_edw/
├── README.md
├── .env.example              # template listing required env vars (no real secrets)
├── .gitignore                # excludes .env, raw data dumps, venv/, __pycache__/
├── requirements.txt
├── docker-compose.yml
├── .github/workflows/ci.yml
├── ingestion/
│   ├── sec_edgar_client.py
│   ├── world_bank_client.py
│   ├── imf_client.py
│   ├── fx_client.py
│   ├── gold_price_client.py
│   ├── prices_client.py
│   └── config/companies.yml
├── dbt/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/          (one staging model per source)
│   │   ├── intermediate/     (cleaning, currency normalization)
│   │   └── marts/
│   │       ├── dim_company.sql
│   │       ├── dim_country.sql
│   │       ├── dim_date.sql
│   │       ├── dim_currency.sql
│   │       ├── fact_financials.sql
│   │       ├── fact_market_prices.sql
│   │       ├── fact_macro_indicators.sql
│   │       └── fact_gold_price.sql
│   └── tests/                # dbt-native tests only: schema.yml tests (not_null,
│                              # unique, relationships) + custom SQL reconciliation tests
├── tests/                     # Python unit/integration tests for the ingestion & pipeline
│   ├── conftest.py            # shared fixtures (mock API responses, sample payloads)
│   ├── test_sec_edgar_client.py
│   ├── test_world_bank_client.py
│   ├── test_fx_client.py
│   ├── test_gold_price_client.py
│   └── test_transformations.py
├── orchestration/
│   └── dagster_pipeline.py
├── dashboards/
│   └── metabase_setup/  or  streamlit_app/
└── docs/
    ├── architecture_diagram.png
    └── project_spec.md
```

**Why two separate `tests/` locations, not one:**

- `dbt/tests/` is dbt-native — SQL-based tests that run against the *warehouse* (e.g. "no null company_key," "every fact row has a matching dimension row," "quarterly sums roughly reconcile to annual filings"). These only make sense inside the dbt project and use dbt's own test runner.
- Root-level `tests/` is standard Python testing (pytest) for the *code* — e.g. "does `sec_edgar_client.py` correctly parse a sample XBRL response," "does the FX normalization function convert correctly," "does a malformed API response get handled without crashing the pipeline." These run via `pytest` in CI, independent of dbt.

Keeping them separate (rather than one giant `tests/` folder) also makes CI faster to reason about: `pytest tests/` runs fast, no warehouse required; `dbt test` runs after the pipeline has actually loaded data.

**On `.env`:**

Every API key (FRED, Alpha Vantage, metals-api.com) belongs in a `.env` file at the repo root — never hardcoded, never committed. The repo ships a `.env.example` instead, which lists the variable names with placeholder values so anyone cloning the repo knows exactly what to fill in:

```
# .env.example — copy to .env and fill in real values; .env itself is gitignored
FRED_API_KEY=your_fred_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
METALS_API_KEY=your_metals_api_key_here
POSTGRES_USER=kubera
POSTGRES_PASSWORD=change_me_locally
POSTGRES_DB=kubera_edw
```

`.gitignore` must include `.env` explicitly, and `docker-compose.yml` / the Python clients read secrets via `os.environ` (e.g. with `python-dotenv` locally) rather than any value ever being typed into a script.

## 9. Data Model: Facts, Dimensions & Grain

### Dimension tables

| Table | Grain | Key Attributes |
|---|---|---|
| `dim_company` | One row per company (SCD Type 2 on sector/classification changes) | company_key, ticker, CIK, legal_name, sector, industry, filer_type (10-K/20-F), effective_from, effective_to, is_current |
| `dim_country` | One row per country | country_key, iso3_code, country_name, region |
| `dim_date` | One row per calendar date | date_key, full_date, fiscal_quarter, fiscal_year, is_period_end |
| `dim_currency` | One row per currency | currency_key, iso_code, currency_name |

### Fact tables

| Table | Grain | Key Measures |
|---|---|---|
| `fact_financials` | One row per company per fiscal filing period | revenue, cost_of_revenue, operating_income, net_income, ebitda (derived), total_debt, cash_and_equivalents, headcount (where disclosed) |
| `fact_market_prices` | One row per company per trading day | close_price_local, close_price_usd, daily_return, volume |
| `fact_macro_indicators` | One row per country per year (or quarter, source-dependent) | gdp, gdp_growth_pct, cpi_inflation_pct, unemployment_pct, fx_rate_to_usd |
| `fact_gold_price` | One row per trading day | gold_price_usd_per_oz (LBMA fixing), daily_change_pct |

All fact tables share `dim_company` (where applicable) and `dim_date` as conformed dimensions, which is what allows a single query/dashboard to join filing-based fundamentals, daily price performance, and country-level macro context together.

> **Note:** `fact_gold_price` is intentionally company-less and country-less — it is a single global daily series (quoted in USD), joined only on `dim_date`. It functions as a cross-cutting benchmark/hedge indicator that any dashboard can overlay against portfolio returns or inflation, rather than being scoped to any one holding.

## 10. KPI & Metrics Framework

| Category | Metric | Business Question Answered |
|---|---|---|
| Fundamental performance | Revenue growth (YoY / QoQ) | Is the underlying business growing? |
| Fundamental performance | EBITDA margin | Is the business becoming more or less profitable? |
| Fundamental performance | Net income growth | Is bottom-line performance improving? |
| Balance sheet health | Net debt / EBITDA | How levered is the company, and is that changing? |
| Balance sheet health | Cash position trend | Is liquidity strengthening or weakening? |
| Market performance | Total return (price, USD-normalized) | What has this position actually returned to Kubera? |
| Market performance | Volatility / drawdown | How risky has this holding been? |
| Market performance | Relative performance vs. sector peers | Is this a winning position within its sector? |
| Portfolio-level | Allocation % by country / sector / currency | How diversified or concentrated is the portfolio? |
| Portfolio-level | FX contribution to return | How much of our return is currency movement vs. the underlying business? |
| Macro overlay | Country GDP growth & inflation trend | Is the macro backdrop supportive of this holding's thesis? |
| Macro overlay | Gold price trend vs. portfolio return | In risk-off/inflationary regimes, is the portfolio's return holding up relative to a traditional safe-haven asset? |

## 11. Data Cadence, Reconciliation & Known Limitations

Important asymmetries to design around, not ignore:

- **Filing frequency differs by filer type.** U.S. domestic filers report quarterly (10-Q) plus annually (10-K). Foreign private issuers (most non-U.S. names on this list) generally only file annually (20-F), with less-standardized interim disclosure (6-K, timing varies by company/country). The warehouse's `fact_financials` grain must tolerate a mixed quarterly/annual cadence rather than assuming uniform quarters across all companies.
- **XBRL tagging is not perfectly uniform** across companies and years — the same economic concept (e.g., "operating income") can appear under slightly different XBRL tags. Staging models need explicit mapping/fallback logic per concept, and this mapping should be documented, not hidden inside a single opaque transformation step.
- **Macro data update lags** — World Bank/IMF figures for a given year are often revised or published with a delay of many months; the pipeline should record a load/version date so that revisions to historical macro figures don't silently overwrite reporting the analyst has already relied on without a visible history.
- **Free-tier API rate limits** (particularly Alpha Vantage) mean market price data should be pulled in bulk/batched and cached locally rather than re-fetched on every pipeline run; Stooq is a viable no-key alternative for historical daily prices at scale.
- **This is fundamentally real, disclosed data — not private operational data.** The project deliberately does not claim to replicate what a real buyout-PE firm sees internally (invoice-level transactions, private management accounts). That is a scope decision, and the README should state it plainly rather than let a reader assume otherwise.

## 12. Build Roadmap / Phases

**Phase 0 — Scope lock.** Finalize the starting company subset (recommend 6-8 companies, 3-4 countries) before writing extraction code. Confirm each company's current SEC filer status directly on EDGAR.

**Phase 1 — Extraction.** Build one client per source (SEC EDGAR, World Bank, FX, prices). Land raw responses as-is (JSON/CSV) in a local raw/landing folder or raw schema — no transformation yet.

**Phase 2 — Staging (dbt).** One staging model per raw source: light cleaning, type casting, renaming, no business logic yet.

**Phase 3 — Conformed dimensions.** Build `dim_company`, `dim_country`, `dim_date`, `dim_currency`; this is where SCD Type 2 logic on `dim_company` should be implemented.

**Phase 4 — Fact tables + currency normalization.** Build `fact_financials`, `fact_market_prices`, `fact_macro_indicators`; apply FX normalization to produce USD-comparable measures.

**Phase 5 — Data quality tests.** dbt tests: not-null/unique on keys, referential integrity between facts and dimensions, and a custom reconciliation test (e.g., sum of quarterly figures roughly ties to annual figures where both exist).

**Phase 6 — Orchestration.** Wrap the pipeline in Dagster (or Airflow), schedule it, add basic run monitoring/logging.

**Phase 7 — BI layer.** Stand up Metabase (or a Streamlit app) on top of the warehouse; build 3-5 dashboards mapped directly to the KPI framework in Section 10.

**Phase 8 — Scale-out.** Once the pipeline is proven correct on the small subset, expand to the full ~40-company universe and validate performance/volume.

**Phase 9 — Polish.** Architecture diagram, final README, CI badge, sample dashboard screenshots committed to the repo.

## 13. Appendix: Assumptions

- Kubera Global Asset Management is entirely fictional; the companies listed are real, but Kubera's ownership/position in them is a simulation for demonstration purposes only, not a factual claim about any actual investor.
- No investment advice, valuation opinion, or trading recommendation is implied anywhere in this project or its outputs.
- All specific tickers, filer classifications, and API endpoint details should be re-verified at the time of build, since filer status, listings, and API terms can change.
- The project's core claim is about data engineering and BI capability — sourcing, modeling, and presenting real data credibly — not about producing genuine investment research.

---

*Kubera_EDW — Project Specification Document*
