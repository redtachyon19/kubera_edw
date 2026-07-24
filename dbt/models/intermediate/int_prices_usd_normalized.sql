-- Intermediate: join daily local-currency prices to FX rates → USD-normalized prices.
-- This is where "FX contribution to return" becomes computable (KPI framework §10).
-- TODO (Phase 4): join stg_prices__daily to stg_fx__rates on (currency, date); handle
--   non-trading-day gaps (forward-fill last available rate); USD tickers pass through at 1.0.

with prices as (
    select * from {{ ref('stg_prices__daily') }}
),

fx as (
    select * from {{ ref('stg_fx__rates') }}
)

select
    -- p.ticker,
    -- p.trade_date,
    -- p.close_local,
    -- f.rate_per_usd,
    -- p.close_local / f.rate_per_usd as close_usd
    *
from prices p
-- left join fx f on ...
