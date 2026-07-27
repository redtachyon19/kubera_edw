
with source as (

    select * from {{ source('raw', 'imf_macro') }}

),

renamed as (

    select
        country_iso3,
        indicator_code,
        cast(year as {{ dbt.type_int() }})      as calendar_year,
        cast(value as {{ type_money() }})   as indicator_value,
        source_file

    from source
    where value is not null

)

select * from renamed
