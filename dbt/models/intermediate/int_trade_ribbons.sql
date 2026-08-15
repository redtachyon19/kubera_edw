-- One row per drawable ribbon: a port, a partner country, a direction.
--
-- The staging model is one row per *industry* within each link. A ribbon on the
-- globe is one line, so this collapses the industry rows into a single link
-- carrying its total value, its dominant industry, and how concentrated that
-- dominance is — which is all the geometry layer needs to size and colour it.
-- The per-industry detail stays in `fact_trade_ribbon` for the panel that opens
-- when a ribbon is clicked.
--
-- **Width comes from PortWatch's own `Total`, not from summing the parts.**
-- Coverage of the thirteen industries is uneven, so a sum systematically
-- understates links where some industries are unreported — and understates them
-- worst on exactly the small, poorly-covered routes where a missing ribbon is
-- most misleading. The sum is kept beside it as `industry_sum_usd_daily` so the
-- gap is visible rather than silently absorbed.

with links as (

    select * from {{ ref('stg_portwatch__trade_ribbons') }}

),

totals as (

    select
        port_id,
        partner_country_iso3,
        flow_direction,
        value_usd_daily as total_usd_daily
    from links
    where is_total

),

parts as (

    select
        port_id,
        partner_country_iso3,
        flow_direction,
        industry,
        hs_section,
        value_usd_daily
    from links
    where not is_total

),

ranked as (

    select
        *,
        row_number() over (
            partition by port_id, partner_country_iso3, flow_direction
            order by value_usd_daily desc
        ) as industry_rank,
        sum(value_usd_daily) over (
            partition by port_id, partner_country_iso3, flow_direction
        ) as industry_sum_usd_daily
    from parts

),

dominant as (

    select
        port_id,
        partner_country_iso3,
        flow_direction,
        industry            as top_industry,
        hs_section          as top_hs_section,
        value_usd_daily     as top_industry_usd_daily,
        industry_sum_usd_daily
    from ranked
    where industry_rank = 1

),

geography as (

    -- Endpoint coordinates are identical across every row of a link; one
    -- arbitrary row supplies them.
    select
        port_id,
        partner_country_iso3,
        flow_direction,
        min(port_name)              as port_name,
        min(port_country_iso3)      as port_country_iso3,
        min(port_country_name)      as port_country_name,
        min(port_latitude)          as port_latitude,
        min(port_longitude)         as port_longitude,
        min(partner_country_name)   as partner_country_name,
        min(partner_latitude)       as partner_latitude,
        min(partner_longitude)      as partner_longitude,
        -- Excludes PortWatch's own 'Total' row, which is a roll-up and not a
        -- fourteenth kind of cargo.
        sum(case when not is_total then 1 else 0 end) as industry_count
    from links
    group by port_id, partner_country_iso3, flow_direction

)

select
    g.port_id,
    g.port_name,
    g.port_country_iso3,
    g.port_country_name,
    g.port_latitude,
    g.port_longitude,

    g.partner_country_iso3,
    g.partner_country_name,
    g.partner_latitude,
    g.partner_longitude,

    g.flow_direction,

    -- Falls back to the summed parts on the minority of links where PortWatch
    -- publishes industries but no total.
    coalesce(t.total_usd_daily, d.industry_sum_usd_daily)   as value_usd_daily,
    t.total_usd_daily,
    d.industry_sum_usd_daily,

    d.top_industry,
    d.top_hs_section,
    d.top_industry_usd_daily,

    -- How much of the link is its largest industry. Near 1.0 is a single-commodity
    -- route — an ore run or a crude lift — and colouring it by that industry is
    -- honest. Near 0.1 is a mixed container service where the dominant industry
    -- is barely more than the runner-up, and the UI should say "mixed" rather
    -- than pick a winner on a rounding error.
    case
        when coalesce(d.industry_sum_usd_daily, 0) > 0
        then d.top_industry_usd_daily / d.industry_sum_usd_daily
    end                                                     as top_industry_share,

    g.industry_count

from geography g
left join totals   t
       on t.port_id = g.port_id
      and t.partner_country_iso3 = g.partner_country_iso3
      and t.flow_direction = g.flow_direction
left join dominant d
       on d.port_id = g.port_id
      and d.partner_country_iso3 = g.partner_country_iso3
      and d.flow_direction = g.flow_direction
