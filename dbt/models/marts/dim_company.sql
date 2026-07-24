-- dim_company — one row per company version. SCD Type 2 on sector/classification changes.
-- Keys/attrs (§9): company_key (surrogate), ticker, cik, legal_name, sector, industry,
--   filer_type (10-K/20-F), effective_from, effective_to, is_current.
-- Seeded from ingestion/config/companies.yml; SCD2 logic tracks attribute changes over time.
-- TODO (Phase 3): build surrogate key, implement SCD2 (snapshot or dbt snapshot-based).

select
    -- company_key: surrogate key over (ticker, effective_from) via dbt_utils (Phase 3)
    -- ticker,
    -- cik,
    -- legal_name,
    -- sector,
    -- industry,
    -- filer_type,
    -- effective_from,
    -- effective_to,
    -- is_current
    cast(null as varchar) as company_key
where false
