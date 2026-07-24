-- Staging: IMF DataMapper macro indicators. One row per country per indicator per year.
-- Secondary/cross-check source against stg_world_bank__macro (§5, §11): where both cover a
-- country-year, the figures should broadly agree; divergence is a data-quality signal.

with source as (

    select * from {{ source('raw', 'imf_macro') }}

),

renamed as (

    select
        country_iso3,
        indicator_code,                                         -- NGDP_RPCH, PCPIPCH
        cast(year as {{ dbt.type_int() }})      as calendar_year,
        cast(value as {{ type_money() }})   as indicator_value,
        source_file

    from source
    where value is not null

)

select * from renamed
