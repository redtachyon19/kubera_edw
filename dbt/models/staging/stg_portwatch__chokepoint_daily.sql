-- Daily transits through the 28 chokepoints, 2019-01-01 onward.
--
-- Two families rather than the ports table's three, because a chokepoint has no
-- import or export side — nothing is landed there, it is only passed through:
--
--   n_*         vessels that transited
--   capacity_*  their aggregate deadweight tonnage, in metric tons
--
-- Capacity is the more honest measure of the two. A transit count treats a
-- feeder and a 400m ULCV as one event each, so a week where the small ships kept
-- moving and the large ones diverted reads as barely changed on counts and falls
-- off a cliff on capacity — which is what actually happened at Bab el-Mandeb.

with source as (

    select * from {{ source('raw', 'portwatch_chokepoint_daily') }}

),

renamed as (

    select
        cast("date" as date)                            as transit_date,
        portid                                          as chokepoint_id,
        portname                                        as chokepoint_name,

        cast(n_total as integer)                        as transits,
        cast(n_container as integer)                    as transits_container,
        cast(n_dry_bulk as integer)                     as transits_dry_bulk,
        cast(n_general_cargo as integer)                as transits_general_cargo,
        cast(n_roro as integer)                         as transits_roro,
        cast(n_tanker as integer)                       as transits_tanker,
        cast(n_cargo as integer)                        as transits_cargo,

        cast(capacity as {{ type_money() }})                as capacity_dwt,
        cast(capacity_container as {{ type_money() }})      as capacity_dwt_container,
        cast(capacity_dry_bulk as {{ type_money() }})       as capacity_dwt_dry_bulk,
        cast(capacity_general_cargo as {{ type_money() }})  as capacity_dwt_general_cargo,
        cast(capacity_roro as {{ type_money() }})           as capacity_dwt_roro,
        cast(capacity_tanker as {{ type_money() }})         as capacity_dwt_tanker,
        cast(capacity_cargo as {{ type_money() }})          as capacity_dwt_cargo

    from source
    where "date" is not null
      and portid is not null

)

select * from renamed
