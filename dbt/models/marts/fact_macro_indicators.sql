-- fact_macro_indicators — one row per country per year (or quarter, source-dependent).
-- Measures (§9): gdp, gdp_growth_pct, cpi_inflation_pct, unemployment_pct, fx_rate_to_usd.
-- FKs: country_key (dim_country), date_key (dim_date, period end).
-- TODO (Phase 4): from stg_world_bank__macro (+ IMF cross-check); attach period-end fx_rate.

with macro as (
    select * from {{ ref('stg_world_bank__macro') }}
)

select
    -- country_key,
    -- date_key,
    -- gdp, gdp_growth_pct, cpi_inflation_pct, unemployment_pct, fx_rate_to_usd
    cast(null as varchar) as country_key
from macro
where false
