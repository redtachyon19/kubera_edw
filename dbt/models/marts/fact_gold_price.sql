-- fact_gold_price — one row per trading day. Intentionally company-less and country-less:
--   a single global USD series, joined only on dim_date (§9). Cross-cutting hedge/benchmark.
-- Measures (§9): gold_price_usd_per_oz (LBMA fixing), daily_change_pct.
-- TODO (Phase 4): from stg_gold__prices; compute daily_change_pct via window lag.

with gold as (
    select * from {{ ref('stg_gold__prices') }}
)

select
    -- date_key,
    -- gold_price_usd_per_oz,
    -- daily_change_pct
    cast(null as int) as date_key
from gold
where false
