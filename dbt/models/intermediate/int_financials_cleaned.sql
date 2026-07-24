-- Intermediate: pivot canonical financial concepts into one row per company per fiscal period.
-- Tolerates mixed cadence: 10-Q quarterly (US) vs 20-F annual (foreign issuers) — do NOT assume
--   uniform quarters (project_spec.md §11).
-- TODO (Phase 4): pivot concept rows → revenue/net_income/operating_income/... columns,
--   derive ebitda, tag period_type (Q vs FY).

with financials as (
    select * from {{ ref('stg_sec_edgar__financials') }}
)

select
    -- ticker,
    -- fiscal_period,
    -- period_type,          -- 'Q' or 'FY'
    -- revenue,
    -- operating_income,
    -- net_income,
    -- ebitda                -- derived
    *
from financials
