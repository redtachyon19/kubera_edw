{{
    config(
        indexes = [
            {'columns': ['port_id', 'partner_country_iso3']},
            {'columns': ['industry_name']},
        ]
    )
}}

-- What is actually in each ribbon, industry by industry.
--
-- The detail behind `fact_trade_ribbon`: click a link on the globe and this is
-- the breakdown that opens. Kept as its own model rather than as an array column
-- on the ribbon so it can also be read the other way round — "which routes carry
-- the world's chemicals" is the same table grouped by industry instead of by
-- link.
--
-- Joined to `dim_industry` so the ordering — and therefore the colour — is the
-- same one the legend uses. Rows whose industry is not in the dimension would be
-- a source change rather than a data gap, so the join is inner and the schema
-- test on the relationship will fail loudly if PortWatch renames a category.

with parts as (

    select * from {{ ref('stg_portwatch__trade_ribbons') }}
    where not is_total

),

industries as (

    select
        industry_name,
        industry_order,
        hs_section
    from {{ ref('dim_industry') }}

),

link_totals as (

    select
        port_id,
        partner_country_iso3,
        flow_direction,
        sum(value_usd_daily) as link_total_usd_daily
    from parts
    group by port_id, partner_country_iso3, flow_direction

)

select
    {{ dbt_utils.generate_surrogate_key([
        'p.port_id', 'p.partner_country_iso3', 'p.flow_direction', 'p.industry'
    ]) }}                                               as trade_ribbon_industry_key,

    p.port_id,
    p.port_name,
    p.port_country_iso3,
    p.partner_country_iso3,
    p.partner_country_name,
    p.flow_direction,

    p.industry                                          as industry_name,
    i.industry_order,
    coalesce(p.hs_section, i.hs_section)                as hs_section,

    p.value_usd_daily,
    p.value_usd_daily * 365                             as value_usd_annual,

    case
        when t.link_total_usd_daily > 0
        then p.value_usd_daily / t.link_total_usd_daily
    end                                                 as share_of_link,

    row_number() over (
        partition by p.port_id, p.partner_country_iso3, p.flow_direction
        order by p.value_usd_daily desc
    )                                                   as industry_rank

from parts p
join industries i on i.industry_name = p.industry
left join link_totals t
       on t.port_id = p.port_id
      and t.partner_country_iso3 = p.partner_country_iso3
      and t.flow_direction = p.flow_direction
