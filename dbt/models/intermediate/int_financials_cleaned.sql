
with facts as (

    select * from {{ ref('stg_sec_edgar__financials') }}

),

concept_map as (

    select * from {{ ref('seed_concept_map') }}

),

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

in_reporting_currency as (

    select
        m.*,
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

    p.operating_income + p.depreciation_amortization as ebitda,
    p.revenue - p.cost_of_revenue                    as gross_profit,
    i.total_debt - i.cash_and_equivalents            as net_debt

from period_measures p
left join instants i
    on  i.cik             = p.cik
    and i.period_end_date = p.period_end_date
