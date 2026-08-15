{{
    config(
        indexes = [
            {'columns': ['port_id']},
            {'columns': ['started_on']},
        ]
    )
}}

-- Disruption events, one row per affected port.
--
-- What this is *for*: annotating a port's tonnage chart. A notch in the series
-- with no explanation looks like a data fault; the same notch labelled "Tropical
-- Cyclone, RED alert, 14–19 March" is the most informative thing on the panel.
--
-- The join to `dim_port` is left, not inner, and deliberately so. PortWatch's
-- disruption records occasionally name a port id that is not in the current
-- ports database — retired entries, mostly — and losing the event entirely
-- because one of its several ports no longer resolves would be worse than
-- carrying it with a null name.

with events as (

    select * from {{ ref('int_port_disruptions') }}

),

ports as (

    select
        port_id,
        port_name,
        country_iso3,
        latitude,
        longitude
    from {{ ref('dim_port') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['e.event_id', 'e.port_id']) }} as port_disruption_key,

    e.event_id,
    e.port_id,
    p.port_name,
    p.country_iso3                                      as port_country_iso3,

    e.event_type,
    -- The source's two-letter codes are not readable on a tooltip.
    case e.event_type
        when 'TC' then 'Tropical cyclone'
        when 'EQ' then 'Earthquake'
        when 'FL' then 'Flood'
        when 'DR' then 'Drought'
        when 'VO' then 'Volcano'
        when 'WF' then 'Wildfire'
        when 'OT' then 'Other'
        else e.event_type
    end                                                 as event_type_name,

    e.event_name,
    e.alert_level,
    e.severity_text,
    e.country_name                                      as event_country_name,

    e.started_on,
    e.ended_on,
    -- Inclusive of both ends: a one-day event lasted a day, not zero.
    ({{ dbt.datediff('e.started_on', 'e.ended_on', 'day') }} + 1) as duration_days,

    -- The event's own centre, which is not the port's position — a cyclone that
    -- closed three ports has one track and three quays.
    e.latitude                                          as event_latitude,
    e.longitude                                         as event_longitude,
    p.latitude                                          as port_latitude,
    p.longitude                                         as port_longitude,

    e.affected_port_count,
    e.affected_population

from events e
left join ports p on p.port_id = e.port_id
