-- Every currency we pull FX for must exist in dim_currency, and every non-USD currency the
-- portfolio needs must have FX coverage. Both directions matter:
--
--   * an FX currency missing from dim_currency means the dimension is not conformed —
--     fact_macro_indicators would join to nothing;
--   * a portfolio currency missing from FX means those companies cannot be USD-normalized,
--     which is precisely how Taiwan/TWD was caught.
--
-- This replaces a hardcoded accepted_values list that had to be edited by hand on every
-- scale-out. A dbt test passes when it returns zero rows.

with fx_currencies as (
    select distinct currency_iso from {{ ref('stg_fx__rates') }}
),

modelled as (
    select distinct iso_code from {{ ref('dim_currency') }}
),

-- Currencies we fetch rates for but never modelled.
unmodelled as (
    select currency_iso as currency, 'in FX feed but not in dim_currency' as problem
    from fx_currencies
    where currency_iso not in (select iso_code from modelled)
),

-- Non-USD currencies the portfolio reports in that have no rate at all.
unconvertible as (
    select iso_code as currency, 'reported currency with no FX coverage' as problem
    from modelled
    where iso_code <> 'USD'
      and iso_code in (select distinct reporting_currency from {{ ref('seed_companies') }})
      and iso_code not in (select currency_iso from fx_currencies)
)

select * from unmodelled
union all
select * from unconvertible
