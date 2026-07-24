-- dim_country — one row per country.
-- Keys/attrs (§9): country_key, iso3_code, country_name, region.
-- TODO (Phase 3): derive from the distinct countries in companies.yml + a region lookup seed.

select
    -- iso3_code as country_key,
    -- iso3_code,
    -- country_name,
    -- region            -- North America / Europe / Asia-Pacific / Latin America
    cast(null as varchar) as country_key
where false
