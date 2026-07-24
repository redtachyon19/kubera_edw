-- Staging: LBMA daily gold fixing (USD/troy oz) from FRED. One row per trading day.
-- TODO (Phase 2): parse FRED observations, cast value to numeric, drop '.' (missing) markers.

with source as (
    select * from {{ source('raw', 'gold_prices') }}
)

select
    -- price_date,
    -- gold_price_usd_per_oz
    *
from source
