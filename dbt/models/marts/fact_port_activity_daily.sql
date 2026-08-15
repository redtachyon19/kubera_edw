{{
    config(
        materialized = 'incremental',
        unique_key = ['port_id', 'activity_date'],
        incremental_strategy = 'delete+insert',
        indexes = [
            {'columns': ['port_id', 'activity_date']},
            {'columns': ['activity_date']},
            {'columns': ['country_iso3']},
        ]
    )
}}

-- The record: one row per port per day, 2019 onward. ~5.7M rows.
--
-- Incremental because a full rebuild of five and a half million rows on every
-- `dbt build` is minutes of work to reproduce bytes that have not changed. The
-- reload window is deliberately generous — PortWatch revises recent history when
-- late AIS arrives, and a strict `> max(date)` watermark would take the first
-- version of every day and never see a correction. `delete+insert` on the port
-- and date pair means a revised day replaces itself rather than duplicating.
--
-- `indexes` is a Postgres-only config and dbt ignores it on adapters that have
-- no such concept, so this stays portable to Snowflake and Databricks (which
-- cluster instead and need no equivalent here).

with daily as (

    select * from {{ ref('stg_portwatch__port_daily') }}

    {% if is_incremental() %}
    -- 45 days of overlap: comfortably wider than the observed publication lag,
    -- and small enough that the incremental run stays under a few seconds.
    where activity_date >= (
        select {{ dbt.dateadd('day', -45, 'max(activity_date)') }}
        from {{ this }}
    )
    {% endif %}

),

ports as (

    select
        port_id,
        country_iso3,
        port_name
    from {{ ref('stg_portwatch__ports') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['d.port_id', 'd.activity_date']) }} as port_activity_key,

    d.activity_date,
    d.port_id,
    -- The daily feed carries its own copy of the name and country; the reference
    -- table wins where they disagree, because that is what every other model
    -- joins to and a port that reads two different countries in two places is
    -- the kind of thing that only surfaces as a wrong total months later.
    coalesce(p.port_name, d.port_name)      as port_name,
    coalesce(p.country_iso3, d.country_iso3) as country_iso3,

    d.port_calls,
    d.port_calls_container,
    d.port_calls_dry_bulk,
    d.port_calls_general_cargo,
    d.port_calls_roro,
    d.port_calls_tanker,

    d.import_tons,
    d.import_tons_container,
    d.import_tons_dry_bulk,
    d.import_tons_general_cargo,
    d.import_tons_roro,
    d.import_tons_tanker,

    d.export_tons,
    d.export_tons_container,
    d.export_tons_dry_bulk,
    d.export_tons_general_cargo,
    d.export_tons_roro,
    d.export_tons_tanker,

    (d.import_tons + d.export_tons)         as total_tons

from daily d
left join ports p on p.port_id = d.port_id
