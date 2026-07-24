-- Staging: FX rates. One row per currency per date.
--
-- DIRECTION MATTERS: Frankfurter is queried with base=USD, so rate_per_usd is "units of the
-- foreign currency per 1 USD" (e.g. JPY 163.82 = ¥163.82 per $1). Converting a foreign-currency
-- amount to USD therefore DIVIDES by this rate. Documented here so Phase 4 cannot invert it.

with source as (

    select * from {{ source('raw', 'fx_rates') }}

),

renamed as (

    select
        cast(rate_date as date)                     as rate_date,
        base_currency,                                          -- always USD for this pull
        currency                                    as currency_iso,
        cast(rate_per_base as {{ dbt.type_float() }}) as rate_per_usd

    from source
    where rate_per_base is not null

)

select * from renamed
