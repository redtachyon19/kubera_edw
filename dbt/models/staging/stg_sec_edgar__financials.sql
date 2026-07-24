-- Staging: SEC EDGAR financial facts. Light cleaning/typing/renaming only — no business logic.
-- Grain: one row per company per taxonomy/concept per unit per reported period.
--
-- Deliberately NOT done here (belongs in intermediate):
--   * picking canonical concepts from the us-gaap/ifrs-full tag candidates
--   * de-duplicating restatements (the same period is re-reported across later filings, so
--     one (cik, concept, period) legitimately has several rows with different accessions)

with source as (

    select * from {{ source('raw', 'sec_edgar_facts') }}

),

renamed as (

    select
        cik,
        ticker,
        entity_name,
        taxonomy,                                                   -- us-gaap | ifrs-full
        concept,                                                    -- raw XBRL tag
        unit,                                                       -- USD, JPY, CNY, shares...
        cast(period_start as date)                  as period_start_date,
        cast(period_end   as date)                  as period_end_date,
        cast(value as {{ dbt.type_float() }})       as value_reported,
        cast(fiscal_year as {{ dbt.type_int() }})   as fiscal_year,
        fiscal_period,                                              -- FY | Q1..Q4
        form,                                                       -- 10-K, 10-Q, 20-F, 6-K
        cast(filed_date as date)                    as filed_date,
        frame,
        accession

    from source
    -- A fact with no period end cannot be placed on the date dimension.
    where period_end is not null

)

select * from renamed
