-- Disruption events fanned out to one row per affected port.
--
-- The source packs the ports one event hit into a single `'port137; port784'`
-- string. This turns that into a relation, so a port's page can ask "what has
-- happened here" with a join instead of a substring match — which would also
-- match `port13` against `port137`.
--
-- **Split with `split_part` against a number series rather than a native
-- unnest.** Every engine has a way to explode a delimited string and they are
-- all different: Postgres wants `string_to_array` + `unnest`, DuckDB
-- `string_split`, Snowflake `LATERAL FLATTEN`, Databricks `explode`. `split_part`
-- is the one spelling all four share, and the widest event in the data hits 37
-- ports, so a series to 40 covers it with room to spare.

{% set max_affected_ports = 40 %}

with events as (

    select * from {{ ref('stg_portwatch__disruptions') }}

),

positions as (

    {% for i in range(1, max_affected_ports + 1) %}
    select {{ i }} as position
    {%- if not loop.last %}
    union all
    {% endif %}
    {%- endfor %}

),

exploded as (

    select
        e.event_id,
        e.event_type,
        e.event_name,
        e.alert_level,
        e.severity_text,
        e.country_name,
        e.started_on,
        e.ended_on,
        e.latitude,
        e.longitude,
        e.affected_port_count,
        e.affected_population,
        -- Ports are joined with '; ', and a stray leading space on later
        -- elements would break the join to the port dimension silently.
        trim(split_part(e.affected_port_ids, ';', p.position)) as port_id

    from events e
    join positions p
      on p.position <= e.affected_port_count

    where e.affected_port_ids is not null

)

select * from exploded
where port_id <> ''
