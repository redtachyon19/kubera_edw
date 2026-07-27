
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
  and quarters_present = 4
  and abs(sum_quarters - annual_reported) / nullif(annual_reported, 0) > 0.02
