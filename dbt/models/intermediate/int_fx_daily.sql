
with currencies as (

    select distinct currency_iso from {{ ref('stg_fx__rates') }}

),

bounds as (

    select min(rate_date) as first_rate_date, max(rate_date) as last_rate_date
    from {{ ref('stg_fx__rates') }}

),

scaffold as (

    select
        d.full_date as rate_date,
        c.currency_iso
    from {{ ref('dim_date') }} d
    cross join currencies c
    cross join bounds b
    where d.full_date >= b.first_rate_date
      and d.full_date <= b.last_rate_date + {{ var('fx_max_carry_forward_days') }}

),

observed as (

    select
        s.rate_date,
        s.currency_iso,
        r.rate_per_usd,
        count(r.rate_per_usd) over (
            partition by s.currency_iso
            order by s.rate_date
            rows between unbounded preceding and current row
        ) as fill_group
    from scaffold s
    left join {{ ref('stg_fx__rates') }} r
        on  r.rate_date    = s.rate_date
        and r.currency_iso = s.currency_iso

),

filled as (

    select
        rate_date,
        currency_iso,
        max(rate_per_usd) over (partition by currency_iso, fill_group) as rate_per_usd,
        (rate_per_usd is null) as is_carried_forward
    from observed

)

select
    rate_date,
    currency_iso,
    rate_per_usd,
    is_carried_forward
from filled
where rate_per_usd is not null

union all

select
    full_date as rate_date,
    'USD'     as currency_iso,
    cast(1 as {{ type_money() }}) as rate_per_usd,
    false     as is_carried_forward
from {{ ref('dim_date') }}
