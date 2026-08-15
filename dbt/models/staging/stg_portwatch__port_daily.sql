-- Daily activity at every port, 2019-01-01 onward. The trade desk's time series.
--
-- Three parallel families of measure, each split the same five ways by vessel
-- class, plus a `_cargo` roll-up that is container + dry bulk + general cargo +
-- roro (everything but tankers) and an unsuffixed total:
--
--   portcalls_*  vessel arrivals — how *busy* the port is
--   import_*     metric tons landed
--   export_*     metric tons loaded
--
-- Kept wide rather than unpivoted to one row per class. Long form would turn
-- 5.7M rows into 34M for a table whose consumers all want several classes at
-- once, and the columns are a fixed, known set rather than an open dimension.
--
-- `date` is quoted throughout: PortWatch named the column after a type, and
-- unquoted `cast(date as date)` is ambiguous in more than one engine.

with source as (

    select * from {{ source('raw', 'portwatch_port_daily') }}

),

renamed as (

    select
        cast("date" as date)                    as activity_date,
        portid                                  as port_id,
        portname                                as port_name,
        iso3                                    as country_iso3,

        cast(portcalls as integer)              as port_calls,
        cast(portcalls_container as integer)    as port_calls_container,
        cast(portcalls_dry_bulk as integer)     as port_calls_dry_bulk,
        cast(portcalls_general_cargo as integer) as port_calls_general_cargo,
        cast(portcalls_roro as integer)         as port_calls_roro,
        cast(portcalls_tanker as integer)       as port_calls_tanker,
        cast(portcalls_cargo as integer)        as port_calls_cargo,

        cast(import_tons as {{ type_money() }})               as import_tons,
        cast(import_container as {{ type_money() }})          as import_tons_container,
        cast(import_dry_bulk as {{ type_money() }})           as import_tons_dry_bulk,
        cast(import_general_cargo as {{ type_money() }})      as import_tons_general_cargo,
        cast(import_roro as {{ type_money() }})               as import_tons_roro,
        cast(import_tanker as {{ type_money() }})             as import_tons_tanker,
        cast(import_cargo as {{ type_money() }})              as import_tons_cargo,

        cast(export_tons as {{ type_money() }})               as export_tons,
        cast(export_container as {{ type_money() }})          as export_tons_container,
        cast(export_dry_bulk as {{ type_money() }})           as export_tons_dry_bulk,
        cast(export_general_cargo as {{ type_money() }})      as export_tons_general_cargo,
        cast(export_roro as {{ type_money() }})               as export_tons_roro,
        cast(export_tanker as {{ type_money() }})             as export_tons_tanker,
        cast(export_cargo as {{ type_money() }})              as export_tons_cargo

    from source
    where "date" is not null
      and portid is not null

)

select * from renamed
