-- Staging: FX rates (base USD). One row per currency per date.
-- TODO (Phase 2): normalize to (date, currency_iso, rate_to_usd), cast, dedupe.

with source as (
    select * from {{ source('raw', 'fx_rates') }}
)

select
    -- rate_date,
    -- currency_iso,      -- GBP, JPY, TWD, ...
    -- rate_per_usd       -- units of currency per 1 USD (or invert — document the direction)
    *
from source
