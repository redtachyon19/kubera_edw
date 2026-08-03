
with universe as (

    select distinct country_iso3
    from {{ ref('seed_companies') }}

),

reference as (

    select * from {{ ref('country_regions') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['u.country_iso3']) }} as country_key,
    u.country_iso3                              as iso3_code,
    coalesce(r.country_name, u.country_iso3)    as country_name,
    r.region,
    r.sub_region

from universe u
left join reference r
    on r.country_iso3 = u.country_iso3
