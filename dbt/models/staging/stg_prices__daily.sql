-- Staging: daily market prices (Stooq / Alpha Vantage). One row per ticker per trading day.
-- TODO (Phase 2): unify Stooq CSV and Alpha Vantage JSON shapes into a common schema.

with source as (
    select * from {{ source('raw', 'market_prices') }}
)

select
    -- ticker,
    -- trade_date,
    -- open, high, low, close_local, volume
    *
from source
