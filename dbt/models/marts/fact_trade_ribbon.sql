{{
    config(
        indexes = [
            {'columns': ['port_id']},
            {'columns': ['partner_country_iso3']},
            {'columns': ['port_country_iso3']},
            {'columns': ['value_usd_daily']},
        ]
    )
}}

-- The ribbons: one row per port → partner-country → direction link.
--
-- Everything the globe needs to draw a flow — two endpoints with coordinates, a
-- value for the thickness, an industry for the colour — plus the ranks that let
-- a caller ask for "the top 300 links worldwide" or "everything through
-- Rotterdam" without pulling 200,000 rows to sort them.
--
-- The per-industry breakdown behind each link lives in
-- `fact_trade_ribbon_industry`, which is what opens when a ribbon is clicked.

with ribbons as (

    select * from {{ ref('int_trade_ribbons') }}

),

ports as (

    select
        port_id,
        tonnage_rank,
        recent_tons
    from {{ ref('dim_port') }}

)

select
    {{ dbt_utils.generate_surrogate_key([
        'r.port_id', 'r.partner_country_iso3', 'r.flow_direction'
    ]) }}                                                   as trade_ribbon_key,

    r.port_id,
    r.port_name,
    r.port_country_iso3,
    r.port_country_name,
    r.port_latitude,
    r.port_longitude,

    r.partner_country_iso3,
    r.partner_country_name,
    r.partner_latitude,
    r.partner_longitude,

    r.flow_direction,
    r.value_usd_daily,
    -- Annualised, because a daily dollar figure on a trade route reads as
    -- implausibly small — $2.9 a day between Abbot Point and Afghanistan is a
    -- real number and a meaningless one to show.
    r.value_usd_daily * 365                                 as value_usd_annual,

    r.total_usd_daily,
    r.industry_sum_usd_daily,
    r.top_industry,
    r.top_hs_section,
    r.top_industry_usd_daily,
    r.top_industry_share,
    r.industry_count,

    -- A link whose largest industry is under a third of it is a mixed service,
    -- and colouring it by that industry would overstate what is known. The UI
    -- draws these neutral.
    (r.top_industry_share >= 0.34)                          as is_industry_dominant,

    p.tonnage_rank                                          as port_tonnage_rank,

    row_number() over (order by r.value_usd_daily desc)     as value_rank,
    row_number() over (
        partition by r.port_id, r.flow_direction
        order by r.value_usd_daily desc
    )                                                       as value_rank_in_port,
    row_number() over (
        partition by r.port_country_iso3, r.flow_direction
        order by r.value_usd_daily desc
    )                                                       as value_rank_in_country

from ribbons r
left join ports p on p.port_id = r.port_id
