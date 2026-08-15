-- Port activity rolled up to weeks.
--
-- The daily series is the record, but it is not what a chart should read. Seven
-- and a half years of daily points is ~2,770 per port, which no line on a screen
-- can resolve and no API should ship; and the daily signal is dominated by a
-- weekday cycle — ports are quieter at weekends — that has nothing to do with
-- trade and swamps the trend the reader came for. Weeks remove that cycle
-- exactly, because it is exactly one week long.
--
-- `date_trunc('week', ...)` is Monday-based in Postgres, DuckDB, Snowflake and
-- Databricks alike, so the bucket boundaries survive a move between them.
--
-- Partial weeks are kept rather than filtered. PortWatch publishes mid-week with
-- a few days' lag, so the newest bucket is always short — dropping it would mean
-- the desk never shows the most recent data, and flagging it lets the UI mark
-- the point as provisional instead.

with daily as (

    select * from {{ ref('stg_portwatch__port_daily') }}

),

weekly as (

    select
        port_id,
        cast(date_trunc('week', activity_date) as date)  as week_start,

        count(*)                                         as days_observed,
        min(activity_date)                               as first_day,
        max(activity_date)                               as last_day,

        sum(port_calls)                                  as port_calls,
        sum(port_calls_container)                        as port_calls_container,
        sum(port_calls_dry_bulk)                         as port_calls_dry_bulk,
        sum(port_calls_general_cargo)                    as port_calls_general_cargo,
        sum(port_calls_roro)                             as port_calls_roro,
        sum(port_calls_tanker)                           as port_calls_tanker,

        sum(import_tons)                                 as import_tons,
        sum(import_tons_container)                       as import_tons_container,
        sum(import_tons_dry_bulk)                        as import_tons_dry_bulk,
        sum(import_tons_general_cargo)                   as import_tons_general_cargo,
        sum(import_tons_roro)                            as import_tons_roro,
        sum(import_tons_tanker)                          as import_tons_tanker,

        sum(export_tons)                                 as export_tons,
        sum(export_tons_container)                       as export_tons_container,
        sum(export_tons_dry_bulk)                        as export_tons_dry_bulk,
        sum(export_tons_general_cargo)                   as export_tons_general_cargo,
        sum(export_tons_roro)                            as export_tons_roro,
        sum(export_tons_tanker)                          as export_tons_tanker

    from daily
    group by port_id, cast(date_trunc('week', activity_date) as date)

)

select
    *,
    (import_tons + export_tons)   as total_tons,
    (days_observed = 7)           as is_complete_week
from weekly
