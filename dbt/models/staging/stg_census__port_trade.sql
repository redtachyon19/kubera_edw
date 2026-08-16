{{
    config(
        enabled = (env_var('CENSUS_API_KEY', '') | trim | length) > 20
    )
}}

-- US imports and exports by port of entry, partner country and HS chapter.
--
-- The deep-dive layer under the global ribbons: PortWatch estimates tonnage and
-- infers an industry from vessel draft, while this is the customs record of what
-- was actually in the boxes. Same ports, same globe, real commodity names.
--
-- **Enabled only when `CENSUS_API_KEY` is set.** Every data endpoint under
-- api.census.gov began requiring a key in 2026 — the published "500 requests a
-- day without one" is out of date — so on a checkout without a key there is no
-- source table to select from and this whole branch of the DAG switches off
-- rather than failing the build. The global PortWatch layer does not depend on
-- it.
--
-- Imports and exports arrive as two separate endpoints with different value
-- columns (`GEN_VAL_MO` against `ALL_VAL_MO`), already normalised to `value_usd`
-- by the extractor, so they union cleanly here.

with imports as (

    select * from {{ source('raw', 'census_port_trade_imports') }}

),

exports as (

    select * from {{ source('raw', 'census_port_trade_exports') }}

),

combined as (

    select * from imports
    union all
    select * from exports

),

renamed as (

    select
        -- `time` arrives as "YYYY-MM"; the first of the month is the grain.
        cast(month || '-01' as date)                    as trade_month,
        flow                                            as flow_direction,

        port_code,
        port_name,
        country_code                                    as partner_country_code,
        country_name                                    as partner_country_name,

        hs_chapter,
        hs_chapter_name,

        cast(value_usd as {{ type_money() }})           as value_usd,
        cast(vessel_value_usd as {{ type_money() }})    as vessel_value_usd,
        cast(vessel_weight_kg as {{ type_money() }})    as vessel_weight_kg,
        cast(container_value_usd as {{ type_money() }}) as container_value_usd

    from combined
    where month is not null
      and port_code is not null

)

select * from renamed
-- Census reports a row for every code it tracks, including the ones that moved
-- nothing. Zero-value rows are ~70% of the table and carry no information a
-- missing row would not.
where value_usd > 0

  -- **Census rolls up on BOTH dimensions and marks each with '-'.** There is a
  -- "TOTAL FOR ALL COUNTRIES" row per port and a "TOTAL FOR ALL PORTS" row per
  -- country, and each is exactly the sum of the detail beside it. Summing with
  -- either left in doubles the answer; with both, quadruples it. Measured on
  -- June 2025 chapter 27, the all-ports row alone was 50% of the total, and the
  -- annual figures came out at 1.92x the published FT-900 until this was added.
  -- Neither is filterable through the API — SUMMARY_LVL=DET does not remove
  -- them — so it has to happen here.
  and port_code <> '-'
  and partner_country_code <> '-'
