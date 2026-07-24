-- fact_macro_indicators — one row per country per year.
--
-- World Bank publishes annually, so the grain is country-year and each row is anchored to the
-- Dec 31 date_key of its year. The four indicators arrive long (one row per indicator) and are
-- pivoted wide here so a dashboard can read GDP, growth, inflation and unemployment together.
--
-- IMF is carried alongside as an independent cross-check rather than blended in: where both
-- sources cover a country-year, divergence is a data-quality signal worth seeing, and silently
-- averaging them would hide exactly that.
--
-- fx_rate_to_usd is the year-end rate for the country's domestic currency (§9).

with world_bank as (

    select
        country_iso3,
        calendar_year,
        max(case when indicator = 'gdp'               then indicator_value end) as gdp,
        max(case when indicator = 'gdp_growth_pct'    then indicator_value end) as gdp_growth_pct,
        max(case when indicator = 'cpi_inflation_pct' then indicator_value end) as cpi_inflation_pct,
        max(case when indicator = 'unemployment_pct'  then indicator_value end) as unemployment_pct,
        max(loaded_at)                                                          as source_loaded_at
    from {{ ref('stg_world_bank__macro') }}
    group by country_iso3, calendar_year

),

imf as (

    select
        country_iso3,
        calendar_year,
        max(case when indicator_code = 'NGDP_RPCH' then indicator_value end) as imf_gdp_growth_pct,
        max(case when indicator_code = 'PCPIPCH'   then indicator_value end) as imf_cpi_inflation_pct
    from {{ ref('stg_imf__macro') }}
    group by country_iso3, calendar_year

),

country as (

    select country_key, iso3_code, region from {{ ref('dim_country') }}

),

-- One domestic currency per country, taken from the current company versions.
country_currency as (

    select distinct country_iso3, domestic_currency
    from {{ ref('dim_company') }}
    where is_current

),

combined as (

    select
        c.country_key,
        c.iso3_code                     as country_iso3,
        c.region,
        coalesce(wb.calendar_year, imf.calendar_year) as calendar_year,
        wb.gdp,
        wb.gdp_growth_pct,
        wb.cpi_inflation_pct,
        wb.unemployment_pct,
        wb.source_loaded_at,
        imf.imf_gdp_growth_pct,
        imf.imf_cpi_inflation_pct,
        cc.domestic_currency
    from country c
    left join world_bank wb on wb.country_iso3 = c.iso3_code
    left join imf        on imf.country_iso3 = c.iso3_code
                        and imf.calendar_year = wb.calendar_year
    left join country_currency cc on cc.country_iso3 = c.iso3_code

),

with_fx as (

    select
        cb.*,
        fx.rate_per_usd as fx_rate_to_usd
    from combined cb
    left join {{ ref('int_fx_daily') }} fx
        on  fx.currency_iso = cb.domestic_currency
        -- Year-end rate: Dec 31 is frequently a non-trading day, which is precisely why
        -- int_fx_daily is forward-filled.
        and fx.rate_date    = cast(cast(cb.calendar_year as varchar) || '-12-31' as date)

)

select
    country_key,
    cast(calendar_year * 10000 + 1231 as {{ dbt.type_int() }}) as date_key,   -- Dec 31 anchor
    country_iso3,
    region,
    calendar_year,
    domestic_currency,

    gdp,
    gdp_growth_pct,
    cpi_inflation_pct,
    unemployment_pct,
    fx_rate_to_usd,

    -- Independent cross-check, plus the divergence it implies.
    imf_gdp_growth_pct,
    imf_cpi_inflation_pct,
    imf_gdp_growth_pct    - gdp_growth_pct    as gdp_growth_source_diff,
    imf_cpi_inflation_pct - cpi_inflation_pct as cpi_source_diff,

    -- Macro figures are revised for years after publication; this stamps which load produced
    -- the values so a revision is visible rather than silent (§11).
    source_loaded_at

from with_fx
where calendar_year is not null
