-- Staging: World Bank macro indicators. One row per country per indicator per year.
-- TODO (Phase 2): pivot indicator codes → named columns, cast numerics, carry the load/version
--   date so later revisions to historical figures are visible (project_spec.md §11).

with source as (
    select * from {{ source('raw', 'world_bank_macro') }}
)

select
    -- country_iso3,
    -- indicator_code,
    -- indicator_name,
    -- year,
    -- value,
    -- loaded_at
    *
from source
