
with fx_currencies as (
    select distinct currency_iso from {{ ref('stg_fx__rates') }}
),

modelled as (
    select distinct iso_code from {{ ref('dim_currency') }}
),

unmodelled as (
    select currency_iso as currency, 'in FX feed but not in dim_currency' as problem
    from fx_currencies
    where currency_iso not in (select iso_code from modelled)
),

unconvertible as (
    select iso_code as currency, 'reported currency with no FX coverage' as problem
    from modelled
    where iso_code <> 'USD'
      and iso_code in (select distinct reporting_currency from {{ ref('seed_companies') }})
      and iso_code not in (select currency_iso from fx_currencies)
)

select * from unmodelled
union all
select * from unconvertible
