-- fact_market_prices — one row per company per trading day.
-- Measures (§9): close_price_local, close_price_usd, daily_return, volume.
-- FKs: company_key (dim_company), date_key (dim_date).
-- TODO (Phase 4): from int_prices_usd_normalized; compute daily_return via window lag over USD.

with prices as (
    select * from {{ ref('int_prices_usd_normalized') }}
)

select
    -- company_key,
    -- date_key,
    -- close_price_local,
    -- close_price_usd,
    -- daily_return,      -- close_usd / lag(close_usd) - 1
    -- volume
    cast(null as varchar) as company_key
from prices
where false
