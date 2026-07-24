-- Custom reconciliation test (Phase 5): where a company reports BOTH quarterly (10-Q) and an
-- annual (10-K/20-F) figure for a fiscal year, the four quarters should roughly tie to the
-- annual figure. A dbt test passes when it returns ZERO rows — so this selects the violations
-- (companies/years whose quarterly sum deviates from the annual figure beyond tolerance).
--
-- TODO (Phase 5): implement against fact_financials once populated. Tolerance accounts for
--   restatements and rounding; foreign issuers that only file annually are excluded (no quarters).

-- Disabled until Phase 4 populates fact_financials with revenue / fiscal_year / period_type.
-- TODO(phase-4): flip enabled=true once those columns exist.
{{ config(severity='warn', enabled=false) }}

with reconciliation as (
    select
        company_key,
        fiscal_year,
        sum(case when period_type = 'Q' then revenue end) as sum_quarters,
        max(case when period_type = 'FY' then revenue end) as annual_reported
    from {{ ref('fact_financials') }}
    group by 1, 2
)

select *
from reconciliation
where annual_reported is not null
  and sum_quarters is not null
  and abs(sum_quarters - annual_reported) / nullif(annual_reported, 0) > 0.02  -- 2% tolerance
