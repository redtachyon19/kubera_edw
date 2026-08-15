-- The 28 maritime chokepoints, with their recent transit window folded in.
--
-- Same construction as `dim_port`, and the same reason for it: a chokepoint's
-- name and position are useless without knowing whether traffic through it is
-- normal. The comparison window is what turns Bab el-Mandeb from a dot in a
-- strait into the most legible number on the desk.

with chokepoints as (

    select * from {{ ref('stg_portwatch__chokepoints') }}

),

bounds as (

    select
        max(transit_date)                                       as latest_date,
        {{ dbt.dateadd('day', -90, 'max(transit_date)') }}      as recent_from,
        {{ dbt.dateadd('day', -180, 'max(transit_date)') }}     as prior_from,
        -- A year back, so the comparison can also be made against the same
        -- season rather than only against the previous quarter — traffic through
        -- several of these is strongly seasonal.
        {{ dbt.dateadd('day', -455, 'max(transit_date)') }}     as year_ago_from,
        {{ dbt.dateadd('day', -365, 'max(transit_date)') }}     as year_ago_to
    from {{ ref('stg_portwatch__chokepoint_daily') }}

),

windows as (

    select
        d.chokepoint_id,

        sum(case when d.transit_date > b.recent_from then d.transits end)       as recent_transits,
        sum(case when d.transit_date > b.prior_from
                  and d.transit_date <= b.recent_from then d.transits end)      as prior_transits,
        sum(case when d.transit_date > b.year_ago_from
                  and d.transit_date <= b.year_ago_to then d.transits end)      as year_ago_transits,

        sum(case when d.transit_date > b.recent_from then d.capacity_dwt end)   as recent_capacity_dwt,
        sum(case when d.transit_date > b.prior_from
                  and d.transit_date <= b.recent_from then d.capacity_dwt end)  as prior_capacity_dwt,
        sum(case when d.transit_date > b.year_ago_from
                  and d.transit_date <= b.year_ago_to then d.capacity_dwt end)  as year_ago_capacity_dwt,

        sum(case when d.transit_date > b.recent_from then d.transits_container end) as recent_transits_container,
        sum(case when d.transit_date > b.recent_from then d.transits_tanker end)    as recent_transits_tanker,
        sum(case when d.transit_date > b.recent_from then d.transits_dry_bulk end)  as recent_transits_dry_bulk,

        max(d.transit_date)                                                     as last_transit_date

    from {{ ref('stg_portwatch__chokepoint_daily') }} d
    cross join bounds b
    group by d.chokepoint_id

)

select
    {{ dbt_utils.generate_surrogate_key(['c.chokepoint_id']) }} as chokepoint_key,
    c.chokepoint_id,
    c.chokepoint_name,
    c.chokepoint_full_name,
    c.country_iso3,
    c.country_name,
    c.continent,
    c.latitude,
    c.longitude,

    c.industry_top1,
    c.industry_top2,
    c.industry_top3,

    w.recent_transits,
    w.prior_transits,
    w.year_ago_transits,
    w.recent_capacity_dwt,
    w.prior_capacity_dwt,
    w.year_ago_capacity_dwt,
    w.recent_transits_container,
    w.recent_transits_tanker,
    w.recent_transits_dry_bulk,
    w.last_transit_date,

    case
        when coalesce(w.prior_transits, 0) > 0
        then (w.recent_transits - w.prior_transits) / cast(w.prior_transits as {{ type_money() }})
    end                                                         as transits_change,

    -- Capacity is the measure that actually moved during the Red Sea diversions:
    -- small ships kept transiting while the large ones went round the Cape, so
    -- counts held up and deadweight collapsed.
    case
        when coalesce(w.prior_capacity_dwt, 0) > 0
        then (w.recent_capacity_dwt - w.prior_capacity_dwt) / w.prior_capacity_dwt
    end                                                         as capacity_change,

    case
        when coalesce(w.year_ago_capacity_dwt, 0) > 0
        then (w.recent_capacity_dwt - w.year_ago_capacity_dwt) / w.year_ago_capacity_dwt
    end                                                         as capacity_change_year_on_year

from chokepoints c
left join windows w on w.chokepoint_id = c.chokepoint_id
