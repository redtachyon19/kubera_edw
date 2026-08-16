-- Every port on the trade desk, with enough context to rank and classify it.
--
-- The reference table on its own says where a port is. What a reader actually
-- wants to know first is whether it *matters* — so the recent activity window is
-- folded in here, giving one row per port that can drive the globe without a
-- second query. History stays in the fact tables.
--
-- **The dimension is the union of ports PortWatch catalogues and ports PortWatch
-- merely references**, which is not the same set. Dunedin (`port865`) carries
-- 311 trade links in the ribbon dataset and has no row in the ports database at
-- all. Scoping this to the catalogue would have failed referential integrity on
-- those links, and "fixing" that by dropping them would have quietly deleted the
-- South Island of New Zealand from the map. The ribbon rows carry their own
-- coordinates, so such a port is perfectly drawable — it just has no reference
-- entry, which `is_catalogued` records rather than hides. Same shape as
-- `dim_country`, and for the same reason.

with catalogued as (

    select * from {{ ref('stg_portwatch__ports') }}

),

-- Ports named by a trade link but absent from the catalogue. Coordinates and
-- country come from the link itself, which is the only place they exist.
referenced as (

    select
        port_id,
        min(port_name)          as port_name,
        min(port_country_iso3)  as country_iso3,
        min(port_country_name)  as country_name,
        min(port_latitude)      as latitude,
        min(port_longitude)     as longitude
    from {{ ref('stg_portwatch__trade_ribbons') }}
    where port_id not in (select port_id from catalogued)
    group by port_id

),

ports as (

    select
        port_id,
        port_name,
        port_full_name,
        locode,
        country_iso3,
        country_name,
        continent,
        latitude,
        longitude,
        industry_top1,
        industry_top2,
        industry_top3,
        share_country_maritime_import,
        share_country_maritime_export,
        true    as is_catalogued
    from catalogued

    union all

    select
        port_id,
        port_name,
        port_name                                       as port_full_name,
        cast(null as {{ dbt.type_string() }})           as locode,
        country_iso3,
        country_name,
        cast(null as {{ dbt.type_string() }})           as continent,
        latitude,
        longitude,
        cast(null as {{ dbt.type_string() }})           as industry_top1,
        cast(null as {{ dbt.type_string() }})           as industry_top2,
        cast(null as {{ dbt.type_string() }})           as industry_top3,
        cast(null as {{ type_money() }})                as share_country_maritime_import,
        cast(null as {{ type_money() }})                as share_country_maritime_export,
        false   as is_catalogued
    from referenced

),

-- The last 90 days of published activity, and the 90 before it. Anchored to the
-- maximum date in the data rather than to today: PortWatch publishes weekly and
-- lags by several days, so "the last 90 days" measured from now would silently
-- clip the newest — and busiest-looking — window on every run.
bounds as (

    select
        max(activity_date)                                              as latest_date,
        {{ dbt.dateadd('day', -90, 'max(activity_date)') }}             as recent_from,
        {{ dbt.dateadd('day', -180, 'max(activity_date)') }}            as prior_from
    from {{ ref('stg_portwatch__port_daily') }}

),

windows as (

    select
        d.port_id,

        sum(case when d.activity_date > b.recent_from
                 then d.import_tons + d.export_tons end)                as recent_tons,
        sum(case when d.activity_date > b.prior_from
                  and d.activity_date <= b.recent_from
                 then d.import_tons + d.export_tons end)                as prior_tons,
        sum(case when d.activity_date > b.recent_from
                 then d.port_calls end)                                 as recent_port_calls,
        sum(case when d.activity_date > b.recent_from
                 then d.import_tons end)                                as recent_import_tons,
        sum(case when d.activity_date > b.recent_from
                 then d.export_tons end)                                as recent_export_tons,

        -- The vessel-class split of the recent window is what makes a port
        -- classifiable as a container hub against an oil terminal, which is a
        -- more useful filter than raw size.
        sum(case when d.activity_date > b.recent_from
                 then d.import_tons_container + d.export_tons_container end) as recent_tons_container,
        sum(case when d.activity_date > b.recent_from
                 then d.import_tons_dry_bulk + d.export_tons_dry_bulk end)   as recent_tons_dry_bulk,
        sum(case when d.activity_date > b.recent_from
                 then d.import_tons_tanker + d.export_tons_tanker end)       as recent_tons_tanker,

        max(d.activity_date)                                            as last_activity_date

    from {{ ref('stg_portwatch__port_daily') }} d
    cross join bounds b
    group by d.port_id

),

-- What the cargo crossing this quay is *worth*, as against how much it weighs.
--
-- The two are genuinely different questions and rank ports differently: a crude
-- terminal moves enormous tonnage of low-value cargo, a container hub the
-- reverse. Tonnage is measured from vessel draft; this is summed from the trade
-- links, which is the only dollar figure PortWatch attaches to a port.
--
-- Only the `is_total` rows are summed. The thirteen industry rows beneath each
-- link are a breakdown of that same total, so including them would count every
-- dollar twice.
trade_value as (

    select
        port_id,
        sum(value_usd_daily) as trade_value_usd_daily
    from {{ ref('stg_portwatch__trade_ribbons') }}
    where is_total
    group by port_id

)

select
    {{ dbt_utils.generate_surrogate_key(['p.port_id']) }}   as port_key,
    p.port_id,
    p.port_name,
    p.port_full_name,
    p.locode,
    p.country_iso3,
    p.country_name,
    p.continent,
    p.latitude,
    p.longitude,

    p.industry_top1,
    p.industry_top2,
    p.industry_top3,
    p.share_country_maritime_import,
    p.share_country_maritime_export,
    p.is_catalogued,

    w.recent_tons,
    w.prior_tons,
    w.recent_port_calls,
    w.recent_import_tons,
    w.recent_export_tons,
    w.recent_tons_container,
    w.recent_tons_dry_bulk,
    w.recent_tons_tanker,
    w.last_activity_date,

    v.trade_value_usd_daily,
    v.trade_value_usd_daily * 365                           as trade_value_usd_annual,

    -- Growth against the preceding quarter. Guarded rather than nullif'd on both
    -- sides so a port that went from nothing to something reads as null instead
    -- of infinity.
    case
        when coalesce(w.prior_tons, 0) > 0
        then (w.recent_tons - w.prior_tons) / w.prior_tons
    end                                                     as tons_change,

    -- A global rank makes "is this a big port" answerable without the caller
    -- having to fetch all 2,065 rows to find out.
    row_number() over (order by coalesce(w.recent_tons, 0) desc)        as tonnage_rank,
    row_number() over (
        partition by p.country_iso3
        order by coalesce(w.recent_tons, 0) desc
    )                                                       as tonnage_rank_in_country,

    -- Ranked by value as well as by weight, because the two orders disagree and
    -- the desk lets a reader switch between them.
    row_number() over (
        order by coalesce(v.trade_value_usd_daily, 0) desc
    )                                                       as value_rank

from ports p
left join windows w on w.port_id = p.port_id
left join trade_value v on v.port_id = p.port_id
