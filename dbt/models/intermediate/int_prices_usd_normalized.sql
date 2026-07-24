-- int_prices_usd_normalized — daily prices with a USD-normalized close.
--
-- NOTE ON A REAL SUBTLETY: every holding in this universe trades as a US-listed ADR or
-- domestic share, so the quoted close is ALREADY in USD and this conversion is a no-op today.
-- The join is kept because the model must stay correct if a home-market listing is ever added
-- (e.g. Toyota on the TSE in JPY), and because the explicit rate column makes the "is this
-- USD?" question answerable from the data instead of from tribal knowledge.
--
-- FX uses int_fx_daily, which is forward-filled — a trade date landing on a day with no ECB
-- quote still converts, rather than dropping out of the warehouse.

with prices as (

    select * from {{ ref('stg_prices__daily') }}

),

company as (

    select ticker, domestic_currency, reporting_currency
    from {{ ref('dim_company') }}
    where is_current

),

joined as (

    select
        p.ticker,
        p.trade_date,
        p.open_price,
        p.high_price,
        p.low_price,
        p.close_price,
        p.volume,
        p.price_source,
        -- Benchmarks (SPY, ACWI) are not held companies, so they have no dimension row;
        -- they are USD-quoted ETFs either way.
        coalesce(c.ticker is not null, false) as is_held_position,
        'USD'                                 as quote_currency
    from prices p
    left join company c
        on c.ticker = p.ticker

),

converted as (

    select
        j.*,
        fx.rate_per_usd,
        fx.is_carried_forward as fx_rate_carried_forward
    from joined j
    left join {{ ref('int_fx_daily') }} fx
        on  fx.currency_iso = j.quote_currency
        and fx.rate_date    = j.trade_date

)

select
    ticker,
    trade_date,
    open_price,
    high_price,
    low_price,
    close_price                     as close_price_local,
    close_price / rate_per_usd      as close_price_usd,
    volume,
    quote_currency,
    rate_per_usd,
    fx_rate_carried_forward,
    is_held_position,
    price_source

from converted
