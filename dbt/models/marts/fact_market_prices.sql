-- fact_market_prices — one row per company per trading day.
--
-- daily_return uses lag() over the USD close, partitioned by ticker and ordered by trade_date.
-- Partitioning matters: without it the first day of each ticker would inherit the previous
-- ticker's last price and manufacture an enormous fake return.
--
-- Gaps (weekends, holidays, suspensions) are NOT filled — the lag is over consecutive
-- OBSERVED trading days, which is the correct basis for a return series.
--
-- Currently empty pending an ALPHA_VANTAGE_API_KEY: stooq.com moved its CSV endpoint behind a
-- JavaScript bot check, so it is no longer usable as a keyless source.

with prices as (

    select * from {{ ref('int_prices_usd_normalized') }}
    where is_held_position          -- benchmarks are handled separately, not as holdings

),

company as (

    select ticker, company_key, effective_from, effective_to
    from {{ ref('dim_company') }}

),

matched as (

    select
        p.*,
        c.company_key,
        row_number() over (
            partition by p.ticker, p.trade_date
            order by
                case when c.effective_from <= p.trade_date then 0 else 1 end,
                case when c.effective_from <= p.trade_date then c.effective_from end desc,
                c.effective_from asc
        ) as version_pick
    from prices p
    inner join company c
        on c.ticker = p.ticker

),

with_returns as (

    select
        *,
        lag(close_price_usd) over (
            partition by ticker
            order by trade_date
        ) as prev_close_usd
    from matched
    where version_pick = 1

)

select
    company_key,
    cast(
        extract(year  from trade_date) * 10000
      + extract(month from trade_date) * 100
      + extract(day   from trade_date)
    as {{ dbt.type_int() }})                        as date_key,

    ticker,
    trade_date,
    close_price_local,
    close_price_usd,
    volume,
    quote_currency,
    rate_per_usd,

    -- nullif guards the first observation per ticker (no prior close) and any zero price.
    (close_price_usd / nullif(prev_close_usd, 0)) - 1    as daily_return

from with_returns
