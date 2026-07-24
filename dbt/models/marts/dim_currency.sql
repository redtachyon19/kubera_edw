-- dim_currency — one row per currency.
-- Keys/attrs (§9): currency_key, iso_code, currency_name.
-- TODO (Phase 3): seed from the distinct currencies in companies.yml (USD, GBP, JPY, TWD, ...).

select
    -- iso_code as currency_key,
    -- iso_code,
    -- currency_name
    cast(null as varchar) as currency_key
where false
