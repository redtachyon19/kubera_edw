
-- The country dimension covers every country the macro feed reports, not only
-- the handful that happen to hold an issuer. Scoping it to the portfolio made
-- `fact_macro_indicators` unable to answer "how does this government compare to
-- its peers", which is the whole point of carrying macro data. `has_issuer`
-- keeps the old, narrower view available to anything that wants it.

with issuers as (

    select distinct country_iso3
    from {{ ref('seed_companies') }}

),

published as (

    select
        country_iso3,
        country_name,
        wb_region,
        income_level,
        capital_city,
        capital_latitude,
        capital_longitude
    from {{ ref('stg_world_bank__countries') }}

),

universe as (

    select country_iso3 from issuers
    union
    select country_iso3 from published

),

reference as (

    select * from {{ ref('country_regions') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['u.country_iso3']) }} as country_key,
    u.country_iso3                                             as iso3_code,
    coalesce(r.country_name, p.country_name, u.country_iso3)   as country_name,

    -- The hand-maintained seed wins where it has an opinion: it carries the
    -- house region names the rest of the warehouse groups by. The World Bank
    -- fills in everywhere else, folded onto the same vocabulary.
    coalesce(
        r.region,
        case p.wb_region
            when 'East Asia & Pacific'        then 'Asia-Pacific'
            when 'South Asia'                 then 'Asia-Pacific'
            when 'Europe & Central Asia'      then 'Europe'
            when 'North America'              then 'North America'
            when 'Latin America & Caribbean'  then 'Latin America'
            when 'Sub-Saharan Africa'         then 'Africa'
            when 'Middle East, North Africa, Afghanistan & Pakistan'
                then 'Middle East & North Africa'
            else p.wb_region
        end
    )                                                          as region,
    r.sub_region,

    p.wb_region                                                as world_bank_region,
    p.income_level,
    p.capital_city,
    p.capital_latitude,
    p.capital_longitude,

    (i.country_iso3 is not null)                               as has_issuer

from universe u
left join reference r on r.country_iso3 = u.country_iso3
left join published p on p.country_iso3 = u.country_iso3
left join issuers   i on i.country_iso3 = u.country_iso3
