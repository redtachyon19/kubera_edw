-- dim_date — one row per calendar date (conformed across all fact tables).
-- Keys/attrs (§9): date_key, full_date, fiscal_quarter, fiscal_year, is_period_end.
-- TODO (Phase 3): generate a date spine (dbt_utils.date_spine or adapter range()) and derive
--   calendar/fiscal attributes. Runnable stub below returns an empty typed table.

select
    -- cast(strftime(full_date, '%Y%m%d') as int) as date_key,
    -- full_date,
    -- fiscal_quarter,
    -- fiscal_year,
    -- is_period_end
    cast(null as int) as date_key,
    cast(null as date) as full_date
where false
