-- int_fx_daily — FX rate for EVERY calendar date, forward-filled from the last published rate.
--
-- Why this exists: Frankfurter publishes on ECB business days only, but the dates we need to
-- convert on (fiscal period ends, trade dates) routinely fall on weekends and holidays —
-- Dec 31 lands on a weekend regularly, and that is a period end for five of nine companies.
-- A naive equi-join on rate_date would silently drop those conversions.
--
-- Forward-fill without IGNORE NULLS: Postgres does not support `last_value(... ignore nulls)`,
-- so this uses the portable running-count grouping trick — a running count of non-null rates
-- forms a group id that is constant across each gap, and max() within that group carries the
-- last observed rate forward. Works identically on DuckDB and Postgres.
--
-- USD is emitted explicitly at 1.0 so downstream models can join unconditionally instead of
-- branching on "is this already USD".

with currencies as (

    select distinct currency_iso from {{ ref('stg_fx__rates') }}

),

bounds as (

    select min(rate_date) as first_rate_date, max(rate_date) as last_rate_date
    from {{ ref('stg_fx__rates') }}

),

-- Every (date, currency) pair we could ever be asked to convert on.
scaffold as (

    select
        d.full_date as rate_date,
        c.currency_iso
    from {{ ref('dim_date') }} d
    cross join currencies c
    cross join bounds b
    where d.full_date between b.first_rate_date and b.last_rate_date

),

observed as (

    select
        s.rate_date,
        s.currency_iso,
        r.rate_per_usd,
        -- Constant across each run of nulls; increments only on a published rate.
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

-- The normalization target itself: 1 USD is always 1 USD. Emitted across the FULL date spine,
-- not just the FX publication window — otherwise USD-reporting companies would lose their
-- pre-2015 history purely because Frankfurter has no quotes that far back.
select
    full_date as rate_date,
    'USD'     as currency_iso,
    cast(1 as {{ type_money() }}) as rate_per_usd,
    false     as is_carried_forward
from {{ ref('dim_date') }}
