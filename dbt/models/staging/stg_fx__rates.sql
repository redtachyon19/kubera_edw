
with source as (

    select * from {{ source('raw', 'fx_rates') }}

),

renamed as (

    select
        cast(rate_date as date)                     as rate_date,
        base_currency,
        currency                                    as currency_iso,
        cast(rate_per_base as {{ type_money() }}) as rate_per_usd

    from source
    where rate_per_base is not null

)

select * from renamed
