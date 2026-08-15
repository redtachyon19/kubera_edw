-- The 28 maritime chokepoints — Suez, Panama, Hormuz, Malacca and the rest.
--
-- Same shape as the ports table, because PortWatch models a chokepoint as a
-- degenerate port that vessels pass through rather than call at. They are kept
-- as a separate model rather than folded in with a flag: a transit is not a port
-- call, the daily table for these counts crossings and DWT rather than cargo
-- tons, and mixing them would let a chokepoint be summed into a country's
-- throughput and double-count everything that sails through it.

with source as (

    select * from {{ source('raw', 'portwatch_chokepoints') }}

),

renamed as (

    select
        portid                                              as chokepoint_id,
        portname                                            as chokepoint_name,
        fullname                                            as chokepoint_full_name,
        country                                             as country_name,
        iso3                                                as country_iso3,
        continent,

        cast(lat as {{ type_money() }})                     as latitude,
        cast(lon as {{ type_money() }})                     as longitude,

        cast(vessel_count_total as {{ type_money() }})          as vessel_count_total,
        cast(vessel_count_container as {{ type_money() }})      as vessel_count_container,
        cast(vessel_count_dry_bulk as {{ type_money() }})       as vessel_count_dry_bulk,
        cast(vessel_count_general_cargo as {{ type_money() }})  as vessel_count_general_cargo,
        cast(vessel_count_roro as {{ type_money() }})           as vessel_count_roro,
        cast(vessel_count_tanker as {{ type_money() }})         as vessel_count_tanker,

        nullif(industry_top1, '')                           as industry_top1,
        nullif(industry_top2, '')                           as industry_top2,
        nullif(industry_top3, '')                           as industry_top3

    from source
    where lat is not null
      and lon is not null
      and portid is not null

)

select * from renamed
