{{
    config(
        enabled = (env_var('CENSUS_API_KEY', '') | trim | length) > 20,
        indexes = [
            {'columns': ['port_code', 'trade_month']},
            {'columns': ['trade_month']},
            {'columns': ['industry_name']},
        ]
    )
}}

-- US trade by port of entry, partner country and industry, monthly from 2013.
--
-- The deep-dive layer. Where a PortWatch ribbon says "roughly this much
-- machinery moved through Los Angeles towards China", this says what customs
-- recorded, in dollars, by HS chapter, every month for a decade — with a real
-- time series behind it rather than a single snapshot.
--
-- HS chapters are rolled up to the same thirteen industries the global layer
-- uses, via `seed_hs_industry`, so both layers colour from one legend. The
-- chapter detail is kept alongside rather than discarded: "Machinery &
-- Electrical Equipment" is the right grain for a colour and the wrong grain for
-- a reader who wants to know it was semiconductors.
--
-- Disabled without `CENSUS_API_KEY`, along with its staging model.

with trade as (

    select * from {{ ref('stg_census__port_trade') }}

),

mapping as (

    select
        hs_chapter,
        industry,
        industry_order,
        industry_fine,
        industry_fine_order,
        hs_section
    from {{ ref('seed_hs_industry') }}

),

month_totals as (

    select
        trade_month,
        flow_direction,
        sum(value_usd) as month_total_usd
    from trade
    group by trade_month, flow_direction

)

select
    {{ dbt_utils.generate_surrogate_key([
        't.trade_month', 't.flow_direction', 't.port_code',
        't.partner_country_code', 't.hs_chapter'
    ]) }}                                               as us_port_trade_key,

    t.trade_month,
    t.flow_direction,

    t.port_code,
    t.port_name,
    t.partner_country_code,
    t.partner_country_name,

    t.hs_chapter,
    t.hs_chapter_name,
    m.industry                                          as industry_name,
    m.industry_order,

    -- The finer split, and the reason this layer is worth having. PortWatch can
    -- only reach HS *section*, so its "Mineral Products" welds crude oil, coal
    -- and gas together with iron ore, cement and salt — useless on a trade desk,
    -- since one is the energy trade and the other is rocks. Census reports
    -- *chapters*, so here chapter 27 stands alone as Energy and 25–26 become
    -- Ores, Stone & Minerals. Everywhere the US layer is on screen this is the
    -- grouping to show; `industry_name` stays only so the two layers can still
    -- be compared like for like.
    m.industry_fine                                     as industry_fine_name,
    m.industry_fine_order,
    m.hs_section,

    t.value_usd,
    t.vessel_value_usd,
    t.vessel_weight_kg,
    t.container_value_usd,

    -- The waterborne share. A "port" code in this dataset covers air and land
    -- crossings too, so this is what separates the quay from the runway — and on
    -- a map of ports, the runway does not belong.
    case
        when t.value_usd > 0
        then t.vessel_value_usd / t.value_usd
    end                                                 as vessel_share,

    case
        when mt.month_total_usd > 0
        then t.value_usd / mt.month_total_usd
    end                                                 as share_of_us_month

from trade t
left join mapping m on m.hs_chapter = t.hs_chapter
left join month_totals mt
       on mt.trade_month = t.trade_month
      and mt.flow_direction = t.flow_direction
