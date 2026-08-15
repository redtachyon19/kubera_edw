-- The 2,065 ports PortWatch tracks, with the coordinates everything else needs.
--
-- The daily activity table carries no geometry at all — only a `portid`. Nothing
-- can be placed on a globe, aggregated by country, or joined to a trade ribbon
-- without coming through here first, which makes this the join table the whole
-- trade desk hangs off.

with source as (

    select * from {{ source('raw', 'portwatch_ports') }}

),

renamed as (

    select
        portid                                              as port_id,
        portname                                            as port_name,
        fullname                                            as port_full_name,
        nullif(locode, '')                                  as locode,
        country                                             as country_name,
        iso3                                                as country_iso3,
        continent,

        cast(lat as {{ type_money() }})                     as latitude,
        cast(lon as {{ type_money() }})                     as longitude,

        -- Vessel counts here are the port's typical traffic mix, not a series.
        -- They are what makes a port classifiable — a tanker terminal and a
        -- container hub of the same tonnage are not the same place.
        cast(vessel_count_total as {{ type_money() }})          as vessel_count_total,
        cast(vessel_count_container as {{ type_money() }})      as vessel_count_container,
        cast(vessel_count_dry_bulk as {{ type_money() }})       as vessel_count_dry_bulk,
        cast(vessel_count_general_cargo as {{ type_money() }})  as vessel_count_general_cargo,
        cast(vessel_count_roro as {{ type_money() }})           as vessel_count_roro,
        cast(vessel_count_tanker as {{ type_money() }})         as vessel_count_tanker,

        nullif(industry_top1, '')                           as industry_top1,
        nullif(industry_top2, '')                           as industry_top2,
        nullif(industry_top3, '')                           as industry_top3,

        -- What share of its country's seaborne trade moves through this port.
        -- A port at 0.6 export share is a single point of failure for that
        -- economy, which is the thing worth surfacing about it.
        --
        -- **Divided by 100 because the source ships these as percentages** — they
        -- run 0–100 and sum to 100 across each country's ports. Every other share
        -- in the warehouse is a 0–1 fraction (`share_of_country_tons`,
        -- `share_of_link`, `top_industry_share`), and one column in the other
        -- unit is how a panel ends up rendering "9545%".
        cast(share_country_maritime_import as {{ type_money() }}) / 100.0
            as share_country_maritime_import,
        cast(share_country_maritime_export as {{ type_money() }}) / 100.0
            as share_country_maritime_export

    from source

    -- A port with no fix cannot be drawn and cannot anchor a ribbon. Keeping it
    -- would put a null-island marker at 0°N 0°E in the Gulf of Guinea.
    where lat is not null
      and lon is not null
      and portid is not null

)

select * from renamed
