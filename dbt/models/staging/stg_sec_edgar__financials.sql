-- Staging: SEC EDGAR financial facts. Light cleaning/typing/renaming only — no business logic.
-- One row per company per reported concept per fiscal period.
-- TODO (Phase 2): unpack XBRL facts, map us-gaap/ifrs-full tags → canonical concept names
--   (mirror ingestion CONCEPT_TAG_MAP), cast values, standardize fiscal period keys.

with source as (
    select * from {{ source('raw', 'sec_edgar_facts') }}
)

select
    -- cik,
    -- ticker,
    -- concept,
    -- fiscal_period,        -- e.g. CY2023Q4
    -- period_end_date,
    -- value_reported,
    -- unit,                 -- USD, shares, etc.
    -- filing_type           -- 10-K / 10-Q / 20-F
    *
from source
