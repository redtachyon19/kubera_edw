{{
    config(
        indexes = [
            {'columns': ['port_id', 'week_start']},
            {'columns': ['week_start']},
        ]
    )
}}

-- Weekly port activity — the series the charts actually read.
--
-- ~800k rows against the daily table's 5.7M, and one point per week is what a
-- seven-year line chart can resolve anyway. Carries a trailing average so the
-- API does not have to compute one per request, and a share-of-country column
-- so a port's importance to its own economy is answerable without a second
-- aggregate.

with weekly as (

    select * from {{ ref('int_port_activity_weekly') }}

),

ports as (

    select
        port_id,
        port_name,
        country_iso3,
        country_name
    from {{ ref('stg_portwatch__ports') }}

),

country_weeks as (

    select
        p.country_iso3,
        w.week_start,
        sum(w.total_tons) as country_tons
    from weekly w
    join ports p on p.port_id = w.port_id
    group by p.country_iso3, w.week_start

)

select
    {{ dbt_utils.generate_surrogate_key(['w.port_id', 'w.week_start']) }} as port_week_key,

    w.week_start,
    w.port_id,
    p.port_name,
    p.country_iso3,
    p.country_name,

    w.days_observed,
    w.is_complete_week,

    w.port_calls,
    w.port_calls_container,
    w.port_calls_dry_bulk,
    w.port_calls_general_cargo,
    w.port_calls_roro,
    w.port_calls_tanker,

    w.import_tons,
    w.import_tons_container,
    w.import_tons_dry_bulk,
    w.import_tons_general_cargo,
    w.import_tons_roro,
    w.import_tons_tanker,

    w.export_tons,
    w.export_tons_container,
    w.export_tons_dry_bulk,
    w.export_tons_general_cargo,
    w.export_tons_roro,
    w.export_tons_tanker,

    w.total_tons,

    -- A 13-week trailing mean: one quarter, which is long enough to flatten the
    -- noise of a few large vessels arriving together and short enough to still
    -- turn when something real happens.
    avg(w.total_tons) over (
        partition by w.port_id
        order by w.week_start
        rows between 12 preceding and current row
    )                                                       as total_tons_13w_avg,

    -- Same week a year ago, for the year-on-year read that seasonality demands.
    lag(w.total_tons, 52) over (
        partition by w.port_id
        order by w.week_start
    )                                                       as total_tons_year_ago,

    case
        when coalesce(c.country_tons, 0) > 0
        then w.total_tons / c.country_tons
    end                                                     as share_of_country_tons

from weekly w
join ports p on p.port_id = w.port_id
left join country_weeks c
       on c.country_iso3 = p.country_iso3
      and c.week_start = w.week_start
