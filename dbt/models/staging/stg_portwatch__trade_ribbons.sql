-- Port → partner-country trade links, valued in dollars a day and typed by goods.
--
-- This is the only free dataset that gives a *drawable* trade flow: a real port
-- with coordinates at one end, a country with coordinates at the other, a US
-- dollar value, and a named industry carrying its HS sections. It is what the
-- globe's ribbons are made of — thickness from the value, colour from the
-- industry.
--
-- **On the source's framing.** PortWatch publishes these as "value at risk": the
-- daily trade that would be interrupted if that port stopped. Arithmetically
-- that is the same quantity as the daily trade flowing through the port to that
-- partner, which is how it is named here. The framing matters for how it is
-- captioned on screen, not for what the number is.
--
-- **The source's `export`/`import` are named from the PARTNER COUNTRY's point of
-- view, not the port's.** This is the single easiest thing to get backwards here,
-- and getting it backwards reverses every arrow on the globe, so it is worth
-- showing the evidence:
--
--   Shanghai        → United States   import  $334bn/yr
--   Los Angeles-LB  → China           export  $305bn/yr
--
-- Those are the same physical trade — Chinese goods bound for America — measured
-- once at the quay they left and once at the quay they arrived at, which is why
-- the two figures nearly agree. Aggregated to countries the pattern is decisive:
-- US→China reads $141bn from the Chinese side and $182bn from the American side
-- (against ~$150bn in reality), while China→US reads $704bn and $542bn.
--
-- So `daily_import_value_at_risk` is what the *partner* imports across this quay,
-- which means the cargo is **leaving** the port; `daily_export_value_at_risk` is
-- what the partner exports across it, so the cargo is **arriving**. Both are
-- therefore renamed to be relative to the port, where `import`/`export` would
-- forever invite the question "whose?":
--
--   outbound = port → partner country
--   inbound  = partner country → port
--
-- (`fact_us_port_trade_monthly` keeps `import`/`export`, because there the terms
-- are a US customs classification and genuinely unambiguous.)
--
-- Two shape changes are made:
--
-- 1. **Direction becomes a row, not a column.** The source carries export and
--    import value side by side, but a ribbon on a globe points one way. Nearly a
--    quarter of rows have only one side populated, so a wide row would be half
--    empty most of the time.
-- 2. **`Total` is kept, flagged rather than dropped.** It is PortWatch's own
--    figure and not guaranteed to equal the sum of the thirteen industries —
--    coverage of the parts is patchy. Ribbon *width* should come from the total
--    and ribbon *colour* from the parts, so both have to survive.
--
-- Values are already raw US dollars (`unit = 'US Dollars'`, `scale = 'Unit'`),
-- so nothing is rescaled here.

with source as (

    select * from {{ source('raw', 'portwatch_trade_ribbons') }}

),

directed as (

    select
        from_portid                             as port_id,
        from_portname                           as port_name,
        from_country                            as port_country_name,
        from_iso3                               as port_country_iso3,
        cast(from_lat as {{ type_money() }})    as port_latitude,
        cast(from_lon as {{ type_money() }})    as port_longitude,

        to_country                              as partner_country_name,
        to_iso3                                 as partner_country_iso3,
        cast(to_lat as {{ type_money() }})      as partner_latitude,
        cast(to_lon as {{ type_money() }})      as partner_longitude,

        industry,
        nullif(hs_section, '')                  as hs_section,

        'outbound'                              as flow_direction,
        cast(daily_import_value_at_risk as {{ type_money() }}) as value_usd_daily

    from source
    where daily_import_value_at_risk is not null

    union all

    select
        from_portid,
        from_portname,
        from_country,
        from_iso3,
        cast(from_lat as {{ type_money() }}),
        cast(from_lon as {{ type_money() }}),

        to_country,
        to_iso3,
        cast(to_lat as {{ type_money() }}),
        cast(to_lon as {{ type_money() }}),

        industry,
        nullif(hs_section, ''),

        'inbound',
        cast(daily_export_value_at_risk as {{ type_money() }})

    from source
    where daily_export_value_at_risk is not null

)

select
    *,
    (industry = 'Total') as is_total
from directed
where value_usd_daily > 0
  and port_latitude is not null
  and partner_latitude is not null
  -- A link from a port to its own country is domestic coastal traffic. It draws
  -- as a ribbon looping back on itself and tells the reader nothing about who
  -- trades with whom.
  and partner_country_iso3 <> port_country_iso3
