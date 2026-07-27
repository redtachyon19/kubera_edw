
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
