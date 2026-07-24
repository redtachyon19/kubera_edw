-- Staging: LBMA daily gold fixing (USD/troy oz) from FRED. One row per trading day.
--
-- FRED encodes "no observation" as the string "." rather than null (markets closed, holidays).
-- Extraction landed that verbatim; this is the layer that turns it into a real null so the
-- value column can be numeric.

with source as (

    select * from {{ source('raw', 'gold_prices') }}

),

cleaned as (

    select
        cast(price_date as date) as price_date,
        series_id,
        case
            when value_raw = '.' then null
            else cast(value_raw as {{ dbt.type_float() }})
        end as gold_price_usd_per_oz

    from source

)

select * from cleaned
