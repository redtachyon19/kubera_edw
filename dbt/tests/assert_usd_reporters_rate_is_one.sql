-- A USD-reporting company must never be "converted" — its rate must be exactly 1.0 and its
-- USD measures must equal its reported measures.
--
-- This is the guard against the subtle failure the FX join could produce: a missing rate row
-- silently nulling out revenue_usd for seven of nine companies, or a stray non-1.0 rate
-- rescaling figures that were already in USD. Both would look plausible in a dashboard.
--
-- A dbt test passes when it returns zero rows, so this selects violations.

select
    ticker,
    period_end_date,
    period_type,
    reporting_currency,
    rate_per_usd,
    revenue,
    revenue_usd

from {{ ref('fact_financials') }}

where reporting_currency = 'USD'
  and (
        rate_per_usd is null
     or rate_per_usd <> 1.0
     or (revenue is not null and revenue_usd is null)
     or (revenue is not null and abs(revenue_usd - revenue) > 0.01)
  )
