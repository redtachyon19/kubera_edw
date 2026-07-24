-- fact_financials — one row per company per fiscal filing period (mixed quarterly/annual).
--
-- Cadence is deliberately NOT uniform: US domestic filers contribute both FY and Q rows
-- (10-K/10-Q), while foreign private issuers contribute FY rows only (20-F). period_type
-- distinguishes them so an analyst never silently sums a quarter beside a year (§11).
--
-- CURRENCY NORMALIZATION. Measures are carried twice: as reported, and converted to USD.
-- Only Toyota (JPY) and Alibaba (CNY) actually convert — AZN, SHEL and INFY are foreign
-- issuers that nonetheless present their SEC financials in USD, so conversion is an
-- intentional no-op for them, not a missing rate. Frankfurter quotes are "foreign units per
-- 1 USD", so converting to USD DIVIDES by the rate (see stg_fx__rates).

with financials as (

    select * from {{ ref('int_financials_cleaned') }}

),

company as (

    select * from {{ ref('dim_company') }}

),

-- As-of join: attach each period to the company version that was effective when the period
-- closed, so a later reclassification never rewrites historical rows. Periods predating
-- coverage inception fall back to the earliest known version.
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
    period_type,                                -- FY | Q
    reporting_currency,

    -- As reported, in the company's own reporting currency.
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

    -- USD-normalized. Null (not zero) where no rate exists — TM/BABA history predates the
    -- FX pull window, and a fabricated zero would read as a real reported figure.
    rate_per_usd,
    fx_rate_carried_forward,
    revenue          / rate_per_usd             as revenue_usd,
    operating_income / rate_per_usd             as operating_income_usd,
    net_income       / rate_per_usd             as net_income_usd,
    ebitda           / rate_per_usd             as ebitda_usd,
    total_debt       / rate_per_usd             as total_debt_usd,
    net_debt         / rate_per_usd             as net_debt_usd,

    -- Ratio KPIs (§10). Unit-free, so they need no currency conversion.
    ebitda        / nullif(revenue, 0)          as ebitda_margin,
    net_income    / nullif(revenue, 0)          as net_margin,
    gross_profit  / nullif(revenue, 0)          as gross_margin,
    net_debt      / nullif(ebitda, 0)           as net_debt_to_ebitda

from converted
