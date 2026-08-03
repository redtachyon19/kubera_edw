
with universe as (

    select distinct currency_iso
    from {{ ref('seed_companies') }}

    union

    select distinct reporting_currency
    from {{ ref('seed_companies') }}

    union

    select 'USD'

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
