{{
    config(
        materialized = 'table',
        indexes = [
            {'columns': ['chokepoint_id', 'transit_date']},
            {'columns': ['transit_date']},
        ]
    )
}}

-- Daily transits and deadweight through the 28 chokepoints, 2019 onward.
--
-- Rebuilt whole rather than incrementally, unlike its port-level sibling. At
-- ~76k rows the rebuild costs a second, and the columns below are the reason it
-- has to be: the trailing averages and the `lag(..., 365)` year-ago comparison
-- are window functions over the full history. Under an incremental build they
-- would see only the reload slice, so every trailing average would be computed
-- from a truncated window and every year-ago value would come back null —
-- quietly, with no error, on a column the desk reads as a headline number.

with daily as (

    select * from {{ ref('stg_portwatch__chokepoint_daily') }}

),

chokepoints as (

    select
        chokepoint_id,
        chokepoint_name,
        latitude,
        longitude
    from {{ ref('stg_portwatch__chokepoints') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['d.chokepoint_id', 'd.transit_date']) }} as chokepoint_transit_key,

    d.transit_date,
    d.chokepoint_id,
    coalesce(c.chokepoint_name, d.chokepoint_name)  as chokepoint_name,
    c.latitude,
    c.longitude,

    d.transits,
    d.transits_container,
    d.transits_dry_bulk,
    d.transits_general_cargo,
    d.transits_roro,
    d.transits_tanker,
    d.transits_cargo,

    d.capacity_dwt,
    d.capacity_dwt_container,
    d.capacity_dwt_dry_bulk,
    d.capacity_dwt_general_cargo,
    d.capacity_dwt_roro,
    d.capacity_dwt_tanker,
    d.capacity_dwt_cargo,

    avg(d.capacity_dwt) over (
        partition by d.chokepoint_id
        order by d.transit_date
        rows between 6 preceding and current row
    )                                               as capacity_dwt_7d_avg,

    avg(cast(d.transits as {{ type_money() }})) over (
        partition by d.chokepoint_id
        order by d.transit_date
        rows between 6 preceding and current row
    )                                               as transits_7d_avg,

    lag(d.capacity_dwt, 365) over (
        partition by d.chokepoint_id
        order by d.transit_date
    )                                               as capacity_dwt_year_ago

from daily d
left join chokepoints c on c.chokepoint_id = d.chokepoint_id
