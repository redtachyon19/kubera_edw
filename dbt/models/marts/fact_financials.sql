
with financials as (

    select * from {{ ref('int_financials_cleaned') }}

),

company as (

    select * from {{ ref('dim_company') }}

),

matched as (

    select
        f.*,
        c.company_key,
        c.reporting_currency,
        c.country_iso3,
        row_number() over (
            partition by f.cik, f.period_end_date, f.period_type
            order by
                case when c.effective_from <= f.period_end_date then 0 else 1 end,
                case when c.effective_from <= f.period_end_date then c.effective_from end desc,
                c.effective_from asc
        ) as version_pick
    from financials f
    inner join company c
        on c.ticker = f.ticker

),

resolved as (

    select * from matched where version_pick = 1

),

converted as (

    select
        r.*,
        fx.rate_per_usd,
        fx.is_carried_forward as fx_rate_carried_forward
    from resolved r
    left join {{ ref('int_fx_daily') }} fx
        on  fx.currency_iso = r.reporting_currency
        and fx.rate_date    = r.period_end_date

)

select
    company_key,
    cast(
        extract(year  from period_end_date) * 10000
      + extract(month from period_end_date) * 100
      + extract(day   from period_end_date)
    as {{ dbt.type_int() }})                    as date_key,

    ticker,
    cik,
    country_iso3,
    period_end_date,
    fiscal_year,
    period_type,
    reporting_currency,

    revenue,
    cost_of_revenue,
    gross_profit,
    operating_income,
    net_income,
    depreciation_amortization,
    ebitda,
    cash_and_equivalents,
    total_debt,
    net_debt,

    rate_per_usd,
    fx_rate_carried_forward,
    revenue          / rate_per_usd             as revenue_usd,
    operating_income / rate_per_usd             as operating_income_usd,
    net_income       / rate_per_usd             as net_income_usd,
    ebitda           / rate_per_usd             as ebitda_usd,
    total_debt       / rate_per_usd             as total_debt_usd,
    net_debt         / rate_per_usd             as net_debt_usd,

    ebitda        / nullif(revenue, 0)          as ebitda_margin,
    net_income    / nullif(revenue, 0)          as net_margin,
    gross_profit  / nullif(revenue, 0)          as gross_margin,
    net_debt      / nullif(ebitda, 0)           as net_debt_to_ebitda

from converted
