
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
