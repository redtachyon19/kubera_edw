-- Staging: daily market prices. One row per ticker per trading day.
-- Unifies both backends (Stooq CSV / Alpha Vantage JSON) into one shape; the loader already
-- normalized the column names, so this layer only casts and keeps the provenance column.
--
-- NOTE: every holding here is a US-listed ADR or domestic share, so close_price is already
-- USD. The "local vs USD" split in fact_market_prices is therefore a no-op for prices — FX
-- normalization matters for FINANCIALS (TM's JPY, BABA's CNY), not for these quotes.

with source as (

    select * from {{ source('raw', 'market_prices') }}

),

renamed as (

    select
        ticker,
        cast(trade_date as date)                as trade_date,
        cast(open   as {{ dbt.type_float() }})  as open_price,
        cast(high   as {{ dbt.type_float() }})  as high_price,
        cast(low    as {{ dbt.type_float() }})  as low_price,
        cast(close  as {{ dbt.type_float() }})  as close_price,
        cast(volume as {{ dbt.type_float() }})  as volume,
        source                                  as price_source

    from source
    where trade_date is not null

)

select * from renamed
