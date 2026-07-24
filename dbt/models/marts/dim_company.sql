-- dim_company — SCD Type 2. One row per company *version*, not per company.
--
-- Sourced from company_snapshot, which dbt maintains with the `check` strategy: when a tracked
-- attribute changes in companies.yml (a sector reclassification, a filer-type change after
-- re-domestication), the snapshot closes the current row and opens a new one. Facts join to the
-- version effective on their own date, so history is never rewritten by a present-day change.
--
-- DETERMINISTIC effective_from: a company's FIRST version is dated from the seed's valid_from
-- (coverage inception), not from dbt_valid_from — which is the snapshot's run clock and would
-- make every rebuild produce different history. Later versions legitimately use the run clock,
-- since that is genuinely when the change was observed.

with snapshotted as (

    select * from {{ ref('company_snapshot') }}

),

ordered as (

    select
        *,
        row_number() over (
            partition by ticker
            order by dbt_valid_from
        ) as version_number

    from snapshotted

),

versioned as (

    select
        -- Surrogate key is (ticker, version-start) — NOT the ticker alone, since one company
        -- legitimately has several rows here.
        {{ dbt_utils.generate_surrogate_key(['ticker', 'dbt_valid_from']) }} as company_key,

        ticker,
        cik,
        legal_name,
        sector,
        industry,
        filer_type,                                     -- 10-K (domestic) | 20-F (foreign)
        country_iso3,
        currency_iso        as domestic_currency,       -- the country's currency
        reporting_currency,                             -- currency the SEC filings present in
        xbrl_taxonomy,                                  -- verified, not inferred from filer_type
        fiscal_year_end,
        version_number,

        case
            when version_number = 1 then cast(valid_from as date)
            else cast(dbt_valid_from as date)
        end                                     as effective_from,

        cast(dbt_valid_to as date)              as effective_to,     -- null while current
        (dbt_valid_to is null)                  as is_current

    from ordered

)

select * from versioned
