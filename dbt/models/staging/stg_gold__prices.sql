
with source as (

    select * from {{ source('raw', 'gold_prices') }}

),

cleaned as (

    select
        cast(price_date as date) as price_date,
        cast(series_id as {{ dbt.type_string() }}) as series_id,
        cast(source as {{ dbt.type_string() }})    as source,
        case
            when value_raw = '.' then null
            else cast(value_raw as {{ type_money() }})
        end as gold_price_usd

    from source

)

select * from cleaned
