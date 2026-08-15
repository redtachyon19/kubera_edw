-- Events that closed or degraded a port: storms, quakes, floods, and a handful
-- of hand-entered geopolitical entries.
--
-- Mostly GDACS-sourced, so `alertlevel` is GDACS's modelled human-exposure
-- score — green / orange / red — rather than anything about shipping. It is
-- useful as a marker on a port's activity chart, which is where a real
-- disruption shows up as a visible notch in the tonnage series.
--
-- `affectedports` arrives as one delimited string of port ids rather than a
-- relation. It is left as text here and split in `int_port_disruptions`, so the
-- fan-out happens once, downstream, rather than in every query that reads this.

with source as (

    select * from {{ source('raw', 'portwatch_disruptions') }}

),

renamed as (

    select
        cast(eventid as integer)                    as event_id,
        eventtype                                   as event_type,
        nullif(eventname, '')                       as event_name,
        nullif(alertlevel, '')                      as alert_level,
        nullif(severitytext, '')                    as severity_text,
        country                                     as country_name,

        -- PortWatch stores these as epoch milliseconds, unlike the daily tables'
        -- date strings. The same source is inconsistent with itself.
        cast(
            {{ dbt.dateadd('second', 'cast(fromdate as bigint) / 1000', "cast('1970-01-01' as timestamp)") }}
            as date
        )                                           as started_on,
        cast(
            {{ dbt.dateadd('second', 'cast(todate as bigint) / 1000', "cast('1970-01-01' as timestamp)") }}
            as date
        )                                           as ended_on,

        cast(lat as {{ type_money() }})             as latitude,
        cast("long" as {{ type_money() }})          as longitude,

        nullif(affectedports, '')                   as affected_port_ids,
        cast(n_affectedports as integer)            as affected_port_count,
        nullif(affectedpopulation, '')              as affected_population

    from source
    where eventid is not null

)

select * from renamed
