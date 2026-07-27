# Architecture

Rendered as Mermaid rather than a committed image: GitHub renders it inline, it stays diffable
in version control, and it cannot silently go stale the way an exported PNG does.

## Pipeline

```mermaid
flowchart LR
    subgraph sources["Public sources"]
        direction TB
        SEC["SEC EDGAR<br/><i>XBRL companyfacts</i><br/>no key"]
        WB["World Bank<br/><i>macro indicators</i><br/>no key"]
        IMF["IMF DataMapper<br/><i>cross-check</i><br/>no key"]
        FX["Frankfurter<br/><i>daily FX, base USD</i><br/>no key"]
        AV["Alpha Vantage<br/><i>prices + GLD proxy</i><br/>free key"]
    end

    subgraph extract["ingestion/ — Python clients"]
        direction TB
        CLIENTS["throttle · retry/backoff<br/>freshness cache · raw landing"]
    end

    LAND[("data/raw/<br/><i>immutable JSON/CSV</i><br/>gitignored")]
    LOADER["ingestion/load_raw.py<br/><i>the EL dbt does not do</i>"]

    subgraph warehouse["Warehouse — DuckDB (dev) or Neon Postgres (prod)"]
        direction TB
        RAW[("raw.*")]
        STG[("staging.*<br/><i>cast · rename · clean</i>")]
        INT[("intermediate.*<br/><i>FX fill · concept pivot</i>")]
        MARTS[("marts.*<br/><i>4 dims · 4 facts</i>")]
        RAW --> STG --> INT --> MARTS
    end

    BI["dashboards/<br/>Streamlit — 5 KPI tabs"]
    DAG["orchestration/<br/>Dagster — 35 assets, 06:00 daily"]

    SEC & WB & IMF & FX & AV --> CLIENTS --> LAND --> LOADER --> RAW
    MARTS --> BI
    DAG -.orchestrates.-> CLIENTS
    DAG -.orchestrates.-> LOADER
    DAG -.orchestrates.-> STG
```

## Star schema

Conformed dimensions are shared across facts, which is what lets a single query join filing
fundamentals, daily prices and country macro together.

```mermaid
erDiagram
    dim_company ||--o{ fact_financials : "company_key"
    dim_company ||--o{ fact_market_prices : "company_key"
    dim_date    ||--o{ fact_financials : "date_key"
    dim_date    ||--o{ fact_market_prices : "date_key"
    dim_date    ||--o{ fact_macro_indicators : "date_key"
    dim_date    ||--o{ fact_gold_price : "date_key"
    dim_country ||--o{ fact_macro_indicators : "country_key"
    dim_currency ||--o{ fact_financials : "reporting_currency"

    dim_company {
        string company_key PK "SCD2 — one row per VERSION"
        string ticker
        string cik "pinned; XOM's resolves to a reorg holdco"
        string sector
        string filer_type "10-K | 20-F"
        string reporting_currency "verified from XBRL units"
        string xbrl_taxonomy "verified — NOT inferable from filer_type"
        date effective_from
        date effective_to
        bool is_current
    }
    fact_financials {
        string company_key FK
        int date_key FK
        string period_type "FY | Q — cadence is mixed by design"
        float revenue "as reported"
        float revenue_usd "normalized"
        float ebitda "derived, null where D&A untagged"
        float rate_per_usd
    }
    fact_market_prices {
        string company_key FK
        int date_key FK
        float close_price_usd
        float daily_return "lag within ticker"
    }
    fact_macro_indicators {
        string country_key FK
        int date_key FK
        float gdp_growth_pct
        float imf_gdp_growth_pct "independent cross-check"
    }
    fact_gold_price {
        int date_key FK "company-less and country-less by design"
        float gold_price_usd
    }
```

## Why the pieces are where they are

| Decision | Reason |
|---|---|
| Raw lands as **files**, not straight to the warehouse | Extraction stays re-runnable and the warehouse rebuildable without re-hitting rate-limited APIs. |
| A **Python loader** rather than SQL reading files | DuckDB can read local JSON; hosted Postgres cannot. Parsing in Python keeps the dbt models byte-identical across both targets. |
| **dbt** owns transformation only | Models are tested and versioned; the loader owns the EL that dbt deliberately does not do. |
| `dim_date` carries **calendar** attributes only | Five fiscal calendars in the universe — a shared fiscal column would be wrong for most companies, so fiscal period travels on the fact. |
| `fact_gold_price` joins **only** on `dim_date` | It is a single global series, a cross-cutting benchmark rather than a per-holding measure. |
