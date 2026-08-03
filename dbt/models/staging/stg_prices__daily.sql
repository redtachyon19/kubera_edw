
with source as (

    select * from {{ source('raw', 'market_prices') }}

),

renamed as (

    select
        cast(ticker as {{ dbt.type_string() }}) as ticker,
        cast(trade_date as date)                as trade_date,
        cast(open   as {{ type_money() }})  as open_price,
        cast(high   as {{ type_money() }})  as high_price,
        cast(low    as {{ type_money() }})  as low_price,
        cast(close  as {{ type_money() }})  as close_price,
        cast(volume as {{ type_money() }})  as volume,
        cast(source as {{ dbt.type_string() }}) as price_source

    from source
    where trade_date is not null

)

select * from renamed
