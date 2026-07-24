-- SCD Type 2 grain integrity: a ticker may have MANY versions in dim_company, but exactly ONE
-- of them may be current.
--
-- This is the failure mode that makes an SCD2 dimension quietly poisonous: if a snapshot run
-- opens a new version without closing the previous one, every fact joined to that company
-- fans out and doubles. Row counts stay plausible, totals silently inflate, and nothing else
-- in the test suite would notice — not_null and unique on company_key both still pass, because
-- each version legitimately has its own key.
--
-- A dbt test passes when it returns zero rows, so this selects offending tickers.

select
    ticker,
    count(*) as current_versions

from {{ ref('dim_company') }}
where is_current

group by ticker
having count(*) > 1
