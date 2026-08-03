
with source as (

    select * from {{ source('raw', 'world_bank_countries') }}

),

renamed as (

    select
        country_iso3,
        country_iso2,
        country_name,
        wb_region,
        income_level,
        nullif(capital_city, '')                    as capital_city,
        cast(latitude  as {{ type_money() }})       as capital_latitude,
        cast(longitude as {{ type_money() }})       as capital_longitude,
        cast(loaded_at as {{ dbt.type_string() }})  as loaded_at,
        source_file

    from source
    where country_iso3 is not null
      and latitude is not null
      and longitude is not null

)

select * from renamed
