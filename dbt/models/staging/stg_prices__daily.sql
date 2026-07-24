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
        -- Explicit string casts, not just renames: when a source is landed empty (prices are
        -- blocked on an API key), the warehouse infers INTEGER for its columns, and joining
        -- that against a varchar dimension key fails outright. Staging is where types get
        -- pinned, so an empty source still produces a correctly TYPED empty table.
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
