-- dim_currency — one row per currency the warehouse touches.
--
-- Union of BOTH currency roles, which are genuinely different sets: a country's domestic
-- currency (GBP for AZN) and the currency a company actually reports in (USD for AZN). USD is
-- included explicitly since it is the normalization target every measure converts into.

with universe as (

    select distinct currency_iso
    from {{ ref('seed_companies') }}

    union

    select distinct reporting_currency
    from {{ ref('seed_companies') }}

    union

    select 'USD'                                -- normalization target, always present

),

reference as (

    select * from {{ ref('currency_names') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['u.currency_iso']) }} as currency_key,
    u.currency_iso                              as iso_code,
    coalesce(r.currency_name, u.currency_iso)   as currency_name,
    r.minor_unit_digits,
    (u.currency_iso = 'USD')                    as is_reporting_base

from universe u
left join reference r
    on r.currency_iso = u.currency_iso
