-- int_financials_cleaned — canonical financial measures, one row per company per fiscal period.
--
-- Four hard problems are solved here, all consequences of real SEC data (§11):
--
-- 1. NON-UNIFORM TAGGING. The same economic concept appears under different XBRL tags and
--    different taxonomies. Toyota is the sharp case: it MIGRATED from us-gaap (FY2009-2020) to
--    ifrs-full (FY2021+), so one company needs both namespaces across its own history.
--    seed_concept_map resolves tag -> canonical concept with a priority order.
--
-- 2. RESTATEMENTS. companyfacts carries every version of a fact ever filed, so one
--    (company, concept, period) has many rows from successive filings. We keep the
--    most-recently-filed value, breaking ties on tag priority.
--
-- 3. YTD PARTIALS. Duration facts include year-to-date spans (6- or 9-month periods tagged
--    Q2/Q3) that are NOT quarterly figures; summing them beside true quarters double counts.
--    Durations are classified by actual day span and partials are dropped.
--
-- 4. THE fy TRAP. SEC's `fy`/`fp` describe the FILING a fact appeared in, not the period the
--    fact measures — a FY2025 10-K restates FY2023 and FY2024 comparatives, all tagged fy=2025.
--    Grouping on fy therefore produces several rows per fiscal year, each a different period.
--    The period grain here comes from the fact's OWN period_end_date and measured duration;
--    fiscal_year is derived from period_end_date, and fy/fp are never used to define grain.

with facts as (

    select * from {{ ref('stg_sec_edgar__financials') }}

),

concept_map as (

    select * from {{ ref('seed_concept_map') }}

),

-- Resolve raw XBRL tags to canonical concepts; anything unmapped drops out here.
mapped as (

    select
        f.cik,
        f.ticker,
        f.period_start_date,
        f.period_end_date,
        f.filed_date,
        f.unit,
        f.value_reported,
        m.canonical_concept,
        m.priority,
        m.statement,
        case
            when f.period_start_date is null then null
            else f.period_end_date - f.period_start_date
        end as period_days

    from facts f
    inner join concept_map m
        on  m.xbrl_tag = f.concept
        and m.taxonomy = f.taxonomy

),

-- A company reports in exactly one currency; ignore convenience translations in other units.
in_reporting_currency as (

    select
        m.*,
        -- Month the company's fiscal year closes (fiscal_year_end is 'MM-DD').
        cast(substring(s.fiscal_year_end, 1, 2) as {{ dbt.type_int() }}) as fiscal_year_end_month
    from mapped m
    inner join {{ ref('seed_companies') }} s
        on  s.ticker             = m.ticker
        and s.reporting_currency = m.unit

),

classified as (

    select
        *,
        case
            when period_start_date is null              then 'instant'
            when period_days between 350 and 380        then 'annual'
            when period_days between  80 and 100        then 'quarterly'
            else 'partial'
        end as duration_type
    from in_reporting_currency

),

-- One value per (company, concept, period): latest filing wins, best tag breaks ties.
deduplicated as (

    select
        *,
        row_number() over (
            partition by cik, canonical_concept, period_end_date, duration_type
            order by filed_date desc, priority asc
        ) as pick
    from classified
    where duration_type <> 'partial'

),

-- Income-statement measures. These DEFINE the reporting periods.
durations as (

    select
        cik,
        ticker,
        period_end_date,
        fiscal_year_end_month,
        case when duration_type = 'annual' then 'FY' else 'Q' end as period_type,
        canonical_concept,
        value_reported
    from deduplicated
    where pick = 1
      and duration_type in ('annual', 'quarterly')

),

period_measures as (

    select
        cik,
        ticker,
        period_end_date,
        period_type,
        fiscal_year_end_month,
        max(case when canonical_concept = 'revenue'                   then value_reported end) as revenue,
        max(case when canonical_concept = 'cost_of_revenue'           then value_reported end) as cost_of_revenue,
        max(case when canonical_concept = 'operating_income'          then value_reported end) as operating_income,
        max(case when canonical_concept = 'net_income'                then value_reported end) as net_income,
        max(case when canonical_concept = 'depreciation_amortization' then value_reported end) as depreciation_amortization
    from durations
    group by cik, ticker, period_end_date, period_type, fiscal_year_end_month

),

-- Balance-sheet measures are point-in-time, so they attach to whichever period closes on
-- that date rather than defining a period of their own.
instants as (

    select
        cik,
        period_end_date,
        max(case when canonical_concept = 'cash_and_equivalents' then value_reported end) as cash_and_equivalents,
        max(case when canonical_concept = 'total_debt'           then value_reported end) as total_debt
    from deduplicated
    where pick = 1
      and duration_type = 'instant'
    group by cik, period_end_date

)

select
    p.cik,
    p.ticker,
    p.period_end_date,
    p.period_type,
    -- Derived from the period itself, never from SEC's filing-scoped fy (see note 4 above),
    -- and anchored to the COMPANY's fiscal calendar rather than the calendar year. Five of the
    -- nine companies close their year off-cycle (Apple Sep, Microsoft Jun, Toyota/Infosys/
    -- Alibaba Mar), so a period ending after the fiscal year-end month belongs to the NEXT
    -- fiscal year: Apple's quarter ending 2023-12-30 is FY2024, not FY2023. Getting this wrong
    -- silently mixes quarters from adjacent fiscal years and breaks quarterly-to-annual
    -- reconciliation.
    cast(
        case
            when extract(month from p.period_end_date) > p.fiscal_year_end_month
                then extract(year from p.period_end_date) + 1
            else extract(year from p.period_end_date)
        end
    as {{ dbt.type_int() }}) as fiscal_year,

    p.revenue,
    p.cost_of_revenue,
    p.operating_income,
    p.net_income,
    p.depreciation_amortization,
    i.cash_and_equivalents,
    i.total_debt,

    -- Derived measures. Null when an input is missing rather than coalesced to zero, which
    -- would present an unknown as a real figure.
    p.operating_income + p.depreciation_amortization as ebitda,
    p.revenue - p.cost_of_revenue                    as gross_profit,
    i.total_debt - i.cash_and_equivalents            as net_debt

from period_measures p
left join instants i
    on  i.cik             = p.cik
    and i.period_end_date = p.period_end_date
