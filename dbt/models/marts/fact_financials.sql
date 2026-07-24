-- fact_financials — one row per company per fiscal filing period (mixed quarterly/annual).
-- Measures (§9): revenue, cost_of_revenue, operating_income, net_income, ebitda (derived),
--   total_debt, cash_and_equivalents, headcount (where disclosed).
-- FKs: company_key (dim_company), date_key (dim_date, period end).
-- TODO (Phase 4): join int_financials_cleaned to dim_company (SCD2 as-of period) and dim_date.

with financials as (
    select * from {{ ref('int_financials_cleaned') }}
)

select
    -- company_key,
    -- date_key,
    -- period_type,
    -- revenue, cost_of_revenue, operating_income, net_income, ebitda,
    -- total_debt, cash_and_equivalents, headcount
    cast(null as varchar) as company_key
from financials
where false
