-- Staging: World Bank macro indicators. One row per country per indicator per year.
-- loaded_at is carried through deliberately: World Bank revises published figures for years
-- afterwards, and keeping the load stamp is what makes a revision visible instead of silent (§11).

with source as (

    select * from {{ source('raw', 'world_bank_macro') }}

),

renamed as (

    select
        country_iso3,
        country_name,
        indicator,                                              -- gdp, cpi_inflation_pct, ...
        indicator_code,                                         -- NY.GDP.MKTP.CD, ...
        cast(year as {{ dbt.type_int() }})      as calendar_year,
        cast(value as {{ type_money() }})   as indicator_value,
        cast(loaded_at as {{ dbt.type_string() }}) as loaded_at,
        source_file

    from source
    where country_iso3 is not null

)

select * from renamed
