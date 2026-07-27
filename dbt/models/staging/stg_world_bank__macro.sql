
with source as (

    select * from {{ source('raw', 'world_bank_macro') }}

),

renamed as (

    select
        country_iso3,
        country_name,
        indicator,
        indicator_code,
        cast(year as {{ dbt.type_int() }})      as calendar_year,
        cast(value as {{ type_money() }})   as indicator_value,
        cast(loaded_at as {{ dbt.type_string() }}) as loaded_at,
        source_file

    from source
    where country_iso3 is not null

)

select * from renamed
