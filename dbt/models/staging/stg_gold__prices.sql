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
        cast(series_id as {{ dbt.type_string() }}) as series_id,
        cast(source as {{ dbt.type_string() }})    as source,
        -- Deliberately NOT named "per_oz": the unit depends on the series. The current
        -- backend is GLD (USD per SHARE, ~1/10 troy oz) because FRED retired its spot
        -- USD/oz fixing. Calling a ~$370 share price "per ounce" would misstate gold by ~10x.
        case
            when value_raw = '.' then null
            else cast(value_raw as {{ type_money() }})
        end as gold_price_usd

    from source

)

select * from cleaned
