-- fact_gold_price — one row per trading day.
--
-- Intentionally company-less and country-less: a single global USD series joined only on
-- dim_date (§9). It functions as a cross-cutting hedge/benchmark that any dashboard can
-- overlay against portfolio returns or inflation, rather than being scoped to a holding.
--
-- FRED marks non-observation days with "." (already nulled in staging); those rows are dropped
-- here so daily_change_pct is computed over consecutive OBSERVED fixings rather than treating
-- a missing day as a zero-price crash.
--
-- Backend is GLD (SPDR Gold Shares) via Alpha Vantage; FRED retired its spot USD/oz
-- series. series_id and source travel with every row so the provenance is queryable.

with gold as (

    select *
    from {{ ref('stg_gold__prices') }}
    where gold_price_usd is not null

),

with_change as (

    select
        *,
        lag(gold_price_usd) over (order by price_date) as prev_price
    from gold

)

select
    cast(
        extract(year  from price_date) * 10000
      + extract(month from price_date) * 100
      + extract(day   from price_date)
    as {{ dbt.type_int() }})                                as date_key,

    price_date,
    series_id,
    source,
    gold_price_usd,
    (gold_price_usd / nullif(prev_price, 0)) - 1            as daily_change_pct

from with_change
