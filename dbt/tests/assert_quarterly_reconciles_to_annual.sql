-- Custom reconciliation test (Phase 5): where a company reports BOTH quarterly (10-Q) and an
-- annual (10-K/20-F) figure for a fiscal year, the four quarters should roughly tie to the
-- annual figure. A dbt test passes when it returns ZERO rows — so this selects the violations
-- (companies/years whose quarterly sum deviates from the annual figure beyond tolerance).
--
-- TODO (Phase 5): implement against fact_financials once populated. Tolerance accounts for
--   restatements and rounding; foreign issuers that only file annually are excluded (no quarters).

-- Severity is `warn`, not error: a company can legitimately have an incomplete quarterly set
-- in a year (a foreign private issuer filing only some 6-K interims), and that is a coverage
-- observation for the analyst, not a broken pipeline.
{{ config(severity='warn') }}

with by_year as (
    select
        ticker,
        fiscal_year,
        count(case when period_type = 'Q'  then 1 end)     as quarters_present,
        sum(case when period_type = 'Q'  then revenue end) as sum_quarters,
        max(case when period_type = 'FY' then revenue end) as annual_reported
    from {{ ref('fact_financials') }}
    group by 1, 2
)

select
    *,
    abs(sum_quarters - annual_reported) / nullif(annual_reported, 0) as relative_gap
from by_year
where annual_reported is not null
  and sum_quarters is not null
  -- Only compare where a COMPLETE set of four quarters exists; three quarters summing to
  -- less than the year is arithmetic, not a data-quality failure.
  and quarters_present = 4
  and abs(sum_quarters - annual_reported) / nullif(annual_reported, 0) > 0.02  -- 2% tolerance
